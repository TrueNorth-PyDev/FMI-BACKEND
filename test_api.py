"""
Comprehensive API Testing Script - Simulates Postman Collection
Tests all endpoints with populated database
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api"
session = requests.Session()

# Test credentials
INVESTOR1 = {"email": "investor1@privcap.com", "password": "Test123!@#"}
INVESTOR2 = {"email": "investor2@privcap.com", "password": "Test123!@#"}
ADMIN = {"email": "admin@privcap.com", "password": "Admin123!@#"}

def print_test(name, status, details=""):
    symbol = "[PASS]" if status else "[FAIL]"
    print(f"{symbol} {name}")
    if details:
        print(f"      {details}")

def test_auth_flow():
    print("\n=== AUTHENTICATION FLOW ===")
    
    # Test login
    response = session.post(f"{BASE_URL}/accounts/login/", json=INVESTOR1)
    if response.status_code == 200:
        data = response.json()
        access_token = data['tokens']['access']
        session.headers.update({'Authorization': f'Bearer {access_token}'})
        print_test("Login", True, f"Token: {access_token[:20]}...")
        return access_token
    else:
        print_test("Login", False, f"Status: {response.status_code}")
        return None

def test_profile_endpoints(token):
    print("\n=== PROFILE ENDPOINTS ===")
    
    # Get profile
    response = session.get(f"{BASE_URL}/accounts/profile/")
    print_test("GET /accounts/profile/", response.status_code == 200, 
               f"User: {response.json().get('email', 'N/A')}")
    
    # Update profile
    response = session.patch(f"{BASE_URL}/accounts/profile/", 
                            json={"phone_number": "+1111111111"})
    print_test("PATCH /accounts/profile/", response.status_code == 200)

def test_investment_endpoints():
    print("\n=== INVESTMENT ENDPOINTS ===")
    
    # List investments
    response = session.get(f"{BASE_URL}/investments/")
    if response.status_code == 200:
        count = len(response.json().get('results', []))
        print_test("GET /investments/", True, f"Found {count} investments")
    else:
        print_test("GET /investments/", False)
    
    # Get portfolio overview
    response = session.get(f"{BASE_URL}/portfolio/overview/")
    if response.status_code == 200:
        data = response.json()
        value = data.get('key_metrics', {}).get('portfolio_value', 0)
        print_test("GET /portfolio/overview/", True, f"Portfolio Value: ${value:,.2f}")
    else:
        print_test("GET /portfolio/overview/", False)
    
    # Get asset allocation
    response = session.get(f"{BASE_URL}/portfolio/asset-allocation/")
    print_test("GET /portfolio/asset-allocation/", response.status_code == 200)

def test_transfer_endpoints():
    print("\n=== TRANSFER ENDPOINTS ===")
    
    # List transfers
    response = session.get(f"{BASE_URL}/transfers/")
    if response.status_code == 200:
        count = len(response.json().get('results', []))
        print_test("GET /transfers/", True, f"Found {count} transfers")
    else:
        print_test("GET /transfers/", False)
    
    # Get pending transfers
    response = session.get(f"{BASE_URL}/transfers/pending/")
    if response.status_code == 200:
        count = response.json().get('total_count', 0)
        print_test("GET /transfers/pending/", True, f"Pending: {count}")
    else:
        print_test("GET /transfers/pending/", False)

def test_marketplace_endpoints():
    print("\n=== MARKETPLACE ENDPOINTS ===")
    
    # List opportunities
    response = session.get(f"{BASE_URL}/marketplace/opportunities/")
    if response.status_code == 200:
        count = len(response.json().get('results', []))
        print_test("GET /marketplace/opportunities/", True, f"Found {count} opportunities")
        
        # Get first opportunity ID for detail test
        if count > 0:
            opp_id = response.json()['results'][0]['id']
            detail_response = session.get(f"{BASE_URL}/marketplace/opportunities/{opp_id}/")
            print_test(f"GET /marketplace/opportunities/{opp_id}/", 
                      detail_response.status_code == 200)
    else:
        print_test("GET /marketplace/opportunities/", False)
    
    # Get watchlist
    response = session.get(f"{BASE_URL}/marketplace/watchlist/")
    if response.status_code == 200:
        count = len(response.json().get('results', []))
        print_test("GET /marketplace/watchlist/", True, f"Watchlist: {count} items")
    else:
        print_test("GET /marketplace/watchlist/", False)

def test_investor_network():
    print("\n=== INVESTOR NETWORK ===")
    
    # Get investor directory
    response = session.get(f"{BASE_URL}/accounts/investor-network/directory/")
    if response.status_code == 200:
        count = response.json().get('total_count', 0)
        print_test("GET /investor-network/directory/", True, f"Found {count} investors")
    else:
        print_test("GET /investor-network/directory/", False)
    
    # Get connections
    response = session.get(f"{BASE_URL}/accounts/investor-network/connections/")
    if response.status_code == 200:
        count = response.json().get('total_count', 0)
        print_test("GET /investor-network/connections/", True, f"Connections: {count}")
    else:
        print_test("GET /investor-network/connections/", False)

def test_admin_endpoints():
    print("\n=== ADMIN ENDPOINTS (Transfer Approval) ===")
    
    # Login as admin
    response = session.post(f"{BASE_URL}/accounts/login/", json=ADMIN)
    if response.status_code == 200:
        admin_token = response.json()['tokens']['access']
        session.headers.update({'Authorization': f'Bearer {admin_token}'})
        print_test("Admin Login", True)
        
        # Get pending transfers
        response = session.get(f"{BASE_URL}/transfers/pending/")
        if response.status_code == 200 and response.json().get('total_count', 0) > 0:
            transfers = response.json()['pending_transfers']
            transfer_id = transfers[0]['id']
            
            # Approve transfer
            approve_response = session.post(f"{BASE_URL}/transfers/{transfer_id}/approve/")
            print_test(f"POST /transfers/{transfer_id}/approve/", 
                      approve_response.status_code == 200)
            
            # Complete transfer (triggers signal)
            complete_response = session.post(f"{BASE_URL}/transfers/{transfer_id}/complete/")
            print_test(f"POST /transfers/{transfer_id}/complete/", 
                      complete_response.status_code == 200,
                      "Signal should process asset transfer")
        else:
            print_test("No pending transfers to approve", False)
    else:
        print_test("Admin Login", False)

def main():
    print("="*60)
    print("PRIVCAP HUB - COMPREHENSIVE API VERIFICATION")
    print(f"Testing against: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    try:
        # Test authentication
        token = test_auth_flow()
        if not token:
            print("\n[ERROR] Authentication failed. Cannot proceed with tests.")
            return
        
        # Test all endpoints
        test_profile_endpoints(token)
        test_investment_endpoints()
        test_transfer_endpoints()
        test_marketplace_endpoints()
        test_investor_network()
        test_admin_endpoints()
        
        print("\n" + "="*60)
        print("API VERIFICATION COMPLETE")
        print("="*60)
        
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Cannot connect to server. Is it running on port 8000?")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
