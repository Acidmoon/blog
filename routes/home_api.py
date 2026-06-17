"""Homepage fragment APIs."""

from flask import jsonify, render_template, request

from services.activity_heatmap import build_month_activity_heatmap
from services.articles import list_all_tags, list_published_articles
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections


SIDEBAR_SECTION_IDS = {'activity_heatmap'}


def _render_home_section(section: dict) -> str:
    context = section['context']
    return render_template(
        section['template'],
        section_id=section['id'],
        section_name=section['name'],
        articles=context.get('articles'),
        page=context.get('page'),
        total=context.get('total'),
        per_page=context.get('per_page'),
        total_pages=context.get('total_pages'),
        current_tag=context.get('current_tag'),
        all_tags=context.get('all_tags'),
        daily_quote=context.get('daily_quote'),
    )


def register_routes(bp):
    @bp.route('/api/heatmap')
    def api_heatmap():
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        data = build_month_activity_heatmap(year=year, month=month)
        return render_template('home_sections/activity_heatmap.html', activity_heatmap=data)

    @bp.route('/api/home-sections')
    def api_home_sections():
        page = request.args.get('page', 1, type=int)
        tag = request.args.get('tag', '').strip()
        articles, total = list_published_articles(page=page, tag=tag)
        layout = load_home_layout()
        all_home_sections = build_home_sections(
            layout,
            articles=articles,
            page=page,
            total=total,
            current_tag=tag,
            all_tags=list_all_tags(),
        )
        home_sections = [
            section for section in all_home_sections
            if section.get('id') not in SIDEBAR_SECTION_IDS
        ]
        hero = resolve_hero(layout.get('hero'), tag)
        return jsonify({
            'hero': hero,
            'html': ''.join(_render_home_section(section) for section in home_sections),
        })
