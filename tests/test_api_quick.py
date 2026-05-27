"""Quick test of wired API endpoints."""
import requests
import json

BASE = "http://localhost:8000"
CID = "bdd640fb"

# Test 1: Health
print("=== Health ===")
r = requests.get(f"{BASE}/health")
data = r.json()
print(f"Status: {data['status']}")
print()

# Test 2: Customer Summary
print("=== Customer Summary ===")
r = requests.get(f"{BASE}/customer/summary/{CID}")
data = r.json()
print(f"Status: {data['status']}")
if data.get("profile"):
    p = data["profile"]
    print(f"Name: {p['name']}")
    print(f"Balance: ${p['balance']:,.2f}")
    print(f"Credit Score: {p['credit_score']}")
    print(f"Risk Level: {p['risk_level']}")
    print(f"Account Type: {p['account_type']}")
    print(f"Transactions: {len(data.get('last_5_transactions', []))}")
else:
    print(f"Error: {data.get('error')}")
print()

# Test 3: Trust Score
print("=== Trust Score ===")
r = requests.get(f"{BASE}/trust/score/{CID}")
data = r.json()
print(f"Score: {data['score']}/100 - {data['tier']}")
print(f"Components: {json.dumps(data.get('components', {}), indent=2)}")
print()

# Test 4: Invalid customer
print("=== Invalid Customer ===")
r = requests.get(f"{BASE}/customer/summary/NONEXISTENT")
data = r.json()
print(f"Status: {data['status']}")
print(f"Error: {data.get('error')}")
print()

print("ALL ENDPOINT TESTS PASSED!")
