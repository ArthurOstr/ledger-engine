import os
from sqlalchemy.ext.asyncio import create_async_engine

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
DATABASE_URL = os.getenv('DATABASE_URL')

if ENVIRONMENT == 'production':
    engine = create_async_engine(
        DATABASE_URL,
       connect_args={'ssl': 'require'},
        pool_pre_ping=True,
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

