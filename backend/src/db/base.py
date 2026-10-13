from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models.

    Alembic autogenerate relies on ``Base.metadata`` being populated, so every
    model module must be imported before migrations are generated or applied.
    """

    pass

