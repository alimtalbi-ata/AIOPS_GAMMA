FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN useradd --uid 10001 --create-home gamma
USER gamma
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
