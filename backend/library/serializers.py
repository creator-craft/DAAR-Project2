from typing import Any

from rest_framework import serializers

from library.constants import MAX_QUERY_LENGTH
from library.search import Ranking, SearchMode


class SearchParams(serializers.Serializer[dict[str, Any]]):
    q = serializers.CharField(max_length=MAX_QUERY_LENGTH)
    mode = serializers.ChoiceField(
        choices=[mode.value for mode in SearchMode], default=SearchMode.KEYWORD.value
    )
    ranking = serializers.ChoiceField(
        choices=[ranking.value for ranking in Ranking], default=Ranking.PAGERANK.value
    )
    page = serializers.IntegerField(min_value=1, default=1)
