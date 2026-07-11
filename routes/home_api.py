"""Homepage fragment APIs."""

from flask import jsonify, render_template, request

from services.activity_heatmap import build_month_activity_heatmap
from services.articles import list_all_tags, list_published_articles
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections, render_home_section
from services.query_params import QueryParameterError, parse_optional_month, parse_optional_year, parse_positive_page
from services.tagging import normalize_tag_filter


def register_routes(bp):
    @bp.route('/api/heatmap')
    def api_heatmap():
        try:
            year = parse_optional_year(request.args.get('year'))
            month = parse_optional_month(request.args.get('month'))
            data = build_month_activity_heatmap(year=year, month=month)
        except (QueryParameterError, ValueError) as exc:
            return jsonify({'error': str(exc)}), 400
        return render_template('home_sections/activity_heatmap.html', activity_heatmap=data)

    @bp.route('/api/home-sections')
    def api_home_sections():
        try:
            page = parse_positive_page(request.args.get('page'))
            raw_tag = request.args.get('tag', '').strip()
            tag = normalize_tag_filter(raw_tag) if raw_tag else ''
            if raw_tag and not tag:
                raise QueryParameterError('标签格式无效')
        except (QueryParameterError, ValueError) as exc:
            return jsonify({'error': str(exc)}), 400
        articles, total = list_published_articles(page=page, tag=tag)
        layout = load_home_layout()
        home_sections = build_home_sections(
            layout,
            articles=articles,
            page=page,
            total=total,
            current_tag=tag,
            all_tags=list_all_tags(),
            placements=("main",),
            request_context=request.args.to_dict(flat=True),
        )
        hero = resolve_hero(layout.get('hero'), tag)
        return jsonify({
            'hero': hero,
            'html': ''.join(render_home_section(section) for section in home_sections),
        })
