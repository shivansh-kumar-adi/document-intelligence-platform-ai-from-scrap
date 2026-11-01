import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.config import Settings


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def settings(tmp_path):
    value = Settings(database_url="sqlite:///:memory:", upload_dir=tmp_path / "uploads",
                     chroma_dir=tmp_path / "chroma", embedding_provider="hash",
                     generation_provider="extractive", chunk_size=180, chunk_overlap=30)
    value.prepare()
    return value

