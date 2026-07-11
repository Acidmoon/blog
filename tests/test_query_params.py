"""Public query validation keeps pagination and calendar inputs deterministic."""

import pytest

from services.query_params import (
    QueryParameterError,
    parse_optional_month,
    parse_optional_year,
    parse_positive_page,
)


@pytest.mark.parametrize('value', ['0', '-1', 'abc', '100001'])
def test_page_parser_rejects_non_positive_or_unbounded_values(value):
    """Invalid page inputs cannot reach negative slice or offset arithmetic."""
    with pytest.raises(QueryParameterError):
        parse_positive_page(value)


@pytest.mark.parametrize('value', ['0', '13', 'month'])
def test_month_parser_rejects_invalid_calendar_months(value):
    """Invalid months are rejected before calendar construction."""
    with pytest.raises(QueryParameterError):
        parse_optional_month(value)


@pytest.mark.parametrize('value', ['0', '10000', 'year'])
def test_year_parser_rejects_invalid_calendar_years(value):
    """Invalid years cannot escape Python's supported date range."""
    with pytest.raises(QueryParameterError):
        parse_optional_year(value)


def test_public_routes_return_400_for_invalid_pagination_and_calendar_queries(client):
    """HTML and JSON endpoints reject malformed input rather than slicing unpredictably."""
    responses = [
        client.get('/?page=0'),
        client.get('/?tag=AI,AIGC'),
        client.get('/search?q=博客&page=-1'),
        client.get('/api/home-sections?page=not-a-page'),
        client.get('/api/heatmap?month=13'),
        client.get('/api/article/这是我的博客的第一篇文章/comments?page=-1'),
    ]
    assert [response.status_code for response in responses] == [400, 400, 400, 400, 400, 400]


def test_search_rejects_unbounded_query_length(client):
    """Oversized search terms cannot force repeated full-body scans."""
    response = client.get('/search', query_string={'q': 'x' * 201})
    assert response.status_code == 400


def test_heatmap_calendar_boundaries_are_renderable(client):
    """Representable calendar edges render disabled navigation instead of a 500."""
    earliest = client.get('/api/heatmap?year=1&month=1')
    latest = client.get('/api/heatmap?year=9999&month=12')

    assert earliest.status_code == 200
    assert latest.status_code == 200
    assert 'aw__nav--disabled' in earliest.get_data(as_text=True)
    assert 'aw__nav--disabled' in latest.get_data(as_text=True)
