from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from library.search import Ranking, SearchMode, library_stats, run_search
from library.serializers import SearchParams


@api_view(["GET"])
def stats(request: Request) -> Response:
    return Response(library_stats())


@api_view(["GET"])
def search(request: Request) -> Response:
    params = SearchParams(data=request.query_params)
    params.is_valid(raise_exception=True)
    data: dict = params.validated_data  # type: ignore
    return Response(
        run_search(
            data["q"], SearchMode(data["mode"]), Ranking(data["ranking"]), data["page"]
        )
    )
