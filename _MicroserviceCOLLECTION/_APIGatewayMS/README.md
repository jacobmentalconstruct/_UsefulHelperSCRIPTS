# APIGateway v2.0.0
> Dynamic HTTP Gateway that turns Python objects into REST endpoints.

## Setup
* **Deps:** `pip install -r requirements.txt`
* **Env:** `PYTHONPATH=..` (Requires `microservice_std_lib.py` in root)
* **Run:** `python app.py`

## Specs
* **Port:** 8099
* **Input:** Python Object (`backend_core`)
* **Output:** HTTP Server (Blocking or Threaded)