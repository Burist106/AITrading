"""Representative cross-boundary payload factories."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def broker_specification_payload() -> dict[str, Any]:
    return {
        "canonicalSymbol": "XAUUSD",
        "brokerSymbol": "XAUUSD.demo",
        "specificationVersion": "spec-v1",
        "accountCurrency": "USD",
        "contractSize": 100.0,
        "digits": 2,
        "pointSize": 0.01,
        "tickSize": 0.01,
        "tickValue": 0.01,
        "minimumVolume": 0.01,
        "maximumVolume": 100.0,
        "volumeStep": 0.01,
        "stopLevel": 10,
        "calculationMode": "forex",
        "fetchedAt": "2026-08-26T09:00:00+07:00",
    }


@pytest.fixture
def eligibility_payload() -> dict[str, Any]:
    return {
        "policyId": "demo-auto-policy",
        "policyVersion": "v1.0.4",
        "outcome": "ask",
        "evaluatedAt": "2026-08-26T09:00:00+07:00",
        "checks": [
            {
                "key": "strategy_policy",
                "labelTh": "นโยบายกลยุทธ์",
                "state": "pass",
            },
            {
                "key": "minimum_sample_size",
                "labelTh": "จำนวนตัวอย่างขั้นต่ำ",
                "state": "warn",
                "actualValue": 24.0,
                "requiredValue": 30.0,
            },
        ],
    }


@pytest.fixture
def proposal_payload(eligibility_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "proposalVersion": 1,
        "userId": "00000000-0000-4000-8000-000000000002",
        "tradingAccountId": "00000000-0000-4000-8000-000000000003",
        "accountType": "demo",
        "accountCurrency": "USD",
        "brokerServer": "Demo-Server",
        "canonicalSymbol": "XAUUSD",
        "brokerSymbol": "XAUUSD.demo",
        "symbolSpecificationVersion": "spec-v1",
        "direction": "BUY",
        "strategyCode": "bootstrap-fixture",
        "strategyVersion": "v0",
        "eligibilityPolicyVersion": "v1.0.4",
        "riskPolicyVersion": "v1.0.4",
        "entryPrice": 2410.40,
        "stopLossPrice": 2404.90,
        "takeProfitPrice": 2421.95,
        "calculatedVolume": 0.01,
        "requestedVolume": 0.01,
        "approvedVolume": None,
        "maximumPermittedVolume": 0.01,
        "riskAmount": 5.50,
        "riskPct": 0.25,
        "riskReward": 2.10,
        "marketSnapshotId": "00000000-0000-4000-8000-000000000004",
        "featureSnapshotId": "00000000-0000-4000-8000-000000000005",
        "decisionTraceId": "00000000-0000-4000-8000-000000000006",
        "eligibility": eligibility_payload,
        "status": "pending_approval",
        "createdAt": "2026-08-26T09:00:00+07:00",
        "expiresAt": "2026-08-26T09:00:30+07:00",
    }
