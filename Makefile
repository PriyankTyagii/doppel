PY := .venv/bin/python

.PHONY: install v1 control agent agent-http dashboard test acceptance shape

install:            ## Python venv, billing-v2 and dashboard packages
	python3.11 -m venv .venv
	.venv/bin/pip install -q -r billing-v1/requirements.txt -r doppel-agent/requirements.txt
	cd billing-v2 && npm install
	cd dashboard && npm install

v1:                 ## billing-v1 (legacy, Python) on :8001
	cd billing-v1 && ../.venv/bin/uvicorn main:app --port 8001

control:            ## demo-control on :8090; starts and owns billing-v2 on :8002
	cd demo-control && ../.venv/bin/uvicorn app:app --port 8090

agent:              ## Doppel agent on :8000 via the Synapse MCP servers in doppel-agent/mcp.json
	cd doppel-agent && DOPPEL_MODE=mcp ../.venv/bin/uvicorn server:app --port 8000

agent-http:         ## Doppel agent on :8000 calling the REST APIs directly (development, before Synapse)
	cd doppel-agent && DOPPEL_MODE=http ../.venv/bin/uvicorn server:app --port 8000

dashboard:          ## dashboard on :5173
	cd dashboard && npm run dev

test:               ## unit and planted-difference tests (start their own apps on spare ports)
	$(PY) -m pytest -q billing-v1/tests doppel-agent/tests

acceptance:         ## break-it-live acceptance; needs v1, control and agent running
	$(PY) -m pytest tests/acceptance -v -s

shape:              ## v1 and v2 return identical JSON shapes
	$(PY) scripts/shape_check.py
