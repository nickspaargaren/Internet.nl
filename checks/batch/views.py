# Copyright: 2019, NLnet Labs and the Internet.nl contributors
# SPDX-License-Identifier: Apache-2.0
import json

from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_http_methods

from .util import check_valid_user, batch_async_generate_results
from .util import get_site_url, get_report_metadata, list_requests
from .util import register_request
from .responses import api_response, unknown_request_response
from .responses import invalid_url_response, bad_client_request_response
from .responses import general_server_error
from .. import simple_cache_page
from ..models import BatchRequest
from ..models import BatchRequestStatus
from ..models import BatchDomain, BatchDomainStatus


@require_http_methods(['GET', 'POST'])
@check_valid_user
def endpoint_requests(request, *args, **kwargs):
    if request.method == "GET":
        return list_requests(request, *args, **kwargs)
    else:
        return register_request(request, *args, **kwargs)


@require_http_methods(['GET'])
@check_valid_user
def endpoint_request(request, request_id, *args, **kwargs):
    user = kwargs['batch_user']
    try:
        batch_request = BatchRequest.objects.get(
            user=user, request_id=request_id)
    except BatchRequest.DoesNotExist:
        return unknown_request_response()
    provide_progress = request.GET.get('progress')
    provide_progress = provide_progress and provide_progress.lower() == 'true'
    res = {"request": batch_request.to_api_dict()}
    if provide_progress:
        total_domains = BatchDomain.objects.filter(
            batch_request=batch_request).count()
        finished_domains = BatchDomain.objects.filter(
            batch_request=batch_request,
            status__in=(BatchDomainStatus.done,
                        BatchDomainStatus.error)).count()
        res['request']['progress'] = f"{finished_domains}/{total_domains}"
        res['request']['num_domains'] = total_domains
    return api_response(res)


@require_http_methods(['GET'])
@check_valid_user
def endpoint_results(request, request_id, *args, **kwargs):
    user = kwargs['batch_user']
    try:
        batch_request = BatchRequest.objects.get(
            user=user, request_id=request_id)
    except BatchRequest.DoesNotExist:
        return unknown_request_response()

    if batch_request.status != BatchRequestStatus.done:
        return bad_client_request_response("The request is not yet `done`.")
    else:
        if not batch_request.has_report_file():
            batch_async_generate_results.delay(
                user=user,
                batch_request=batch_request,
                site_url=get_site_url(request))
            return bad_client_request_response(
                "The request is not yet `done`.")

        else:
            try:
                batch_request.report_file.open('r')
                data = json.load(batch_request.report_file)
            except Exception:
                return general_server_error("Report could not be generated.")
            finally:
                batch_request.report_file.close()
            return api_response(data)


@require_http_methods(['GET'])
@check_valid_user
def endpoint_metadata_report(request, *args, **kwargs):
    return api_response({"report": get_report_metadata()})


@check_valid_user
def documentation(request, *args, **kwargs):
    return HttpResponseRedirect(
        'https://github.com/NLnetLabs/Internet.nl/blob/master/'
        'documentation/batch_http_api.md')


@require_http_methods(['GET'])
@check_valid_user
def cancel_test(request, request_id, *args, **kwargs):
    user = kwargs['batch_user']
    try:
        batch_request = BatchRequest.objects.get(
            user=user, request_id=request_id)
    except BatchRequest.DoesNotExist:
        return unknown_request_response()

    batch_request.status = BatchRequestStatus.cancelled
    batch_request.save()
    BatchDomain.objects.filter(batch_request=batch_request).update(
       status=BatchDomainStatus.cancelled)
    return JsonResponse(
        dict(
            success=True,
            message="OK",
            data={}))


@check_valid_user
def old_url(request, *args, **kwargs):
    return invalid_url_response()
