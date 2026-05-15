from .example_router import example_router

def create_routers(app):
    app.include_router(example_router)