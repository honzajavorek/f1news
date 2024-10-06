FROM apify/actor-python:3.12

RUN rm -rf /usr/src/app/*
WORKDIR /usr/src/app

COPY . ./

RUN echo "Python version:" \
 && python --version \
 && echo "Pip version:" \
 && pip --version \
 && echo "Installing Poetry:" \
 && pip install --no-cache-dir poetry~=1.7.1 \
 && echo "Installing dependencies:" \
 && poetry config cache-dir /tmp/.poetry-cache \
 && poetry config virtualenvs.in-project true \
 && poetry install --only=main --no-interaction --no-ansi \
 && rm -rf /tmp/.poetry-cache \
 && echo "All installed Python packages:" \
 && pip freeze

RUN poetry run python -m compileall -q ./f1news

CMD ["poetry", "run", "f1news"]
