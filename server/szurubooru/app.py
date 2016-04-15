''' Exports create_app. '''

import falcon
import sqlalchemy
import sqlalchemy.orm
from szurubooru import api, config, errors, middleware

def _on_auth_error(ex, _request, _response, _params):
    raise falcon.HTTPForbidden(
        title='Authentication error', description=str(ex))

def _on_validation_error(ex, _request, _response, _params):
    raise falcon.HTTPBadRequest(title='Validation error', description=str(ex))

def _on_search_error(ex, _request, _response, _params):
    raise falcon.HTTPBadRequest(title='Search error', description=str(ex))

def _on_integrity_error(ex, _request, _response, _params):
    raise falcon.HTTPConflict(
        title='Integrity violation', description=ex.args[0])

def _on_not_found_error(ex, _request, _response, _params):
    raise falcon.HTTPNotFound(title='Not found', description=str(ex))

def _on_processing_error(ex, _request, _response, _params):
    raise falcon.HTTPBadRequest(title='Processing error', description=str(ex))

def create_app():
    ''' Create a WSGI compatible App object. '''
    engine = sqlalchemy.create_engine(
        '{schema}://{user}:{password}@{host}:{port}/{name}'.format(
            schema=config.config['database']['schema'],
            user=config.config['database']['user'],
            password=config.config['database']['pass'],
            host=config.config['database']['host'],
            port=config.config['database']['port'],
            name=config.config['database']['name']))
    session_maker = sqlalchemy.orm.sessionmaker(bind=engine)
    scoped_session = sqlalchemy.orm.scoped_session(session_maker)

    app = falcon.API(
        request_type=api.Request,
        middleware=[
            middleware.RequireJson(),
            middleware.ContextAdapter(),
            middleware.DbSession(scoped_session),
            middleware.Authenticator(),
        ])

    user_list_api = api.UserListApi()
    user_detail_api = api.UserDetailApi()
    tag_list_api = api.TagListApi()
    tag_detail_api = api.TagDetailApi()
    password_reset_api = api.PasswordResetApi()

    app.add_error_handler(errors.AuthError, _on_auth_error)
    app.add_error_handler(errors.IntegrityError, _on_integrity_error)
    app.add_error_handler(errors.ValidationError, _on_validation_error)
    app.add_error_handler(errors.SearchError, _on_search_error)
    app.add_error_handler(errors.NotFoundError, _on_not_found_error)
    app.add_error_handler(errors.ProcessingError, _on_processing_error)

    app.add_route('/users/', user_list_api)
    app.add_route('/user/{user_name}', user_detail_api)
    app.add_route('/tags/', tag_list_api)
    app.add_route('/tag/{tag_name}', tag_detail_api)
    app.add_route('/password-reset/{user_name}', password_reset_api)

    return app
