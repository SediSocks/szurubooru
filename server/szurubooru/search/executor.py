import sqlalchemy
from szurubooru import db, errors
from szurubooru.func import cache
from szurubooru.search import tokens, parser

def _format_dict_keys(source):
    return list(sorted(source.keys()))

def _get_direction(direction, default_direction):
    if direction == tokens.SortToken.SORT_DEFAULT:
        return default_direction
    if direction == tokens.SortToken.SORT_NEGATED_DEFAULT:
        if default_direction == tokens.SortToken.SORT_ASC:
            return tokens.SortToken.SORT_DESC
        elif default_direction == tokens.SortToken.SORT_DESC:
            return tokens.SortToken.SORT_ASC
        assert False
    return direction

class Executor(object):
    '''
    Class for search parsing and execution. Handles plaintext parsing and
    delegates sqlalchemy filter decoration to SearchConfig instances.
    '''

    def __init__(self, search_config):
        self.config = search_config
        self.parser = parser.Parser()

    def execute(self, query_text, page, page_size):
        '''
        Parse input and return tuple containing total record count and filtered
        entities.
        '''
        key = (id(self.config), query_text, page, page_size)
        if cache.has(key):
            return cache.get(key)

        search_query = self.parser.parse(query_text)

        filter_query = self.config.create_filter_query()
        filter_query = filter_query.options(sqlalchemy.orm.lazyload('*'))
        filter_query = self._prepare_db_query(filter_query, search_query, True)
        entities = filter_query \
            .offset((page - 1) * page_size) \
            .limit(page_size) \
            .all()

        count_query = self.config.create_count_query()
        count_query = count_query.options(sqlalchemy.orm.lazyload('*'))
        count_query = self._prepare_db_query(count_query, search_query, False)
        count_statement = count_query \
            .statement \
            .with_only_columns([sqlalchemy.func.count()]) \
            .order_by(None)
        count = db.session.execute(count_statement).scalar()

        ret = (count, entities)
        cache.put(key, ret)
        return ret

    def execute_and_serialize(self, ctx, serializer):
        query = ctx.get_param_as_string('query')
        page = ctx.get_param_as_int('page', default=1, min=1)
        page_size = ctx.get_param_as_int('pageSize', default=100, min=1, max=100)
        count, entities = self.execute(query, page, page_size)
        return {
            'query': query,
            'page': page,
            'pageSize': page_size,
            'total': count,
            'results': [serializer(entity) for entity in entities],
        }

    def _prepare_db_query(self, db_query, search_query, use_sort):
        ''' Parse input and return SQLAlchemy query. '''

        for token in search_query.anonymous_tokens:
            if not self.config.anonymous_filter:
                raise errors.SearchError(
                    'Anonymous tokens are not valid in this context.')
            db_query = self.config.anonymous_filter(
                db_query, token.criterion, token.negated)

        for token in search_query.named_tokens:
            if token.name not in self.config.named_filters:
                raise errors.SearchError(
                    'Unknown named token: %r. Available named tokens: %r.' % (
                        token.name,
                        _format_dict_keys(self.config.named_filters)))
            db_query = self.config.named_filters[token.name](
                db_query, token.criterion, token.negated)

        for token in search_query.special_tokens:
            if token.value not in self.config.special_filters:
                raise errors.SearchError(
                    'Unknown special token: %r. Available special tokens: %r.' % (
                        token.value,
                        _format_dict_keys(self.config.special_filters)))
            db_query = self.config.special_filters[token.value](
                db_query, token.negated)

        if use_sort:
            for token in search_query.sort_tokens:
                if token.name not in self.config.sort_columns:
                    raise errors.SearchError(
                        'Unknown sort token: %r. Available sort tokens: %r.' % (
                            token.name,
                            _format_dict_keys(self.config.sort_columns)))
                column, default_direction = self.config.sort_columns[token.name]
                direction = _get_direction(token.direction, default_direction)
                if direction == token.SORT_ASC:
                    db_query = db_query.order_by(column.asc())
                elif direction == token.SORT_DESC:
                    db_query = db_query.order_by(column.desc())

        db_query = self.config.finalize_query(db_query)
        return db_query
