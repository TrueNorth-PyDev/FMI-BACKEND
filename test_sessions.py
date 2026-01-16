"""
Test session tracking functionality
"""
import requests
import json

BASE_URL = "http://localhost:8000/api"

# Test credentials
INVESTOR1 = {"email": "investor1@privcap.com", "password": "Test123!@#"}

print("="*60)
print("SESSION TRACKING TEST")
print("="*60)

# 1. Login to create session
print("\n1. Logging in to create session...")
response = requests.post(f"{BASE_URL}/accounts/login/", json=INVESTOR1)

if response.status_code == 200:
    data = response.json()
    access_token = data['tokens']['access']
    print(f"   [PASS] Login successful")
    print(f"   Token: {access_token[:30]}...")
    
    # 2. List sessions
    print("\n2. Listing active sessions...")
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(f"{BASE_URL}/accounts/account/sessions/", headers=headers)
    
    if response.status_code == 200:
        sessions_data = response.json()
        sessions = sessions_data.get('sessions', [])
        total = sessions_data.get('total_count', 0)
        
        print(f"   [PASS] Found {total} session(s)")
        
        for session in sessions:
            print(f"\n   Session ID: {session['id']}")
            print(f"   Device: {session['device_name']}")
            print(f"   Location: {session['location']}")
            print(f"   IP: {session['ip_address']}")
            print(f"   Current: {session['is_current']}")
            print(f"   Created: {session['created_at']}")
    else:
        print(f"   [FAIL] Status: {response.status_code}")
        print(f"   Response: {response.text}")
    
    # 3. Login again from "different device" (simulated with different user agent)
    print("\n3. Simulating login from different device...")
    headers_mobile = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
    }
    response = requests.post(f"{BASE_URL}/accounts/login/", json=INVESTOR1, headers=headers_mobile)
    
    if response.status_code == 200:
        print("   [PASS] Second login successful")
        
        # List sessions again
        new_token = response.json()['tokens']['access']
        headers = {'Authorization': f'Bearer {new_token}'}
        response = requests.get(f"{BASE_URL}/accounts/account/sessions/", headers=headers)
        
        if response.status_code == 200:
            sessions_data = response.json()
            total = sessions_data.get('total_count', 0)
            print(f"   [PASS] Now have {total} session(s)")
            
            # Show all sessions
            for session in sessions_data.get('sessions', []):
                current_marker = " (CURRENT)" if session['is_current'] else ""
                print(f"   - {session['device_name']} from {session['ip_address']}{current_marker}")
        else:
            print(f"   [FAIL] Could not list sessions")
    else:
        print(f"   [FAIL] Second login failed")
    
else:
    print(f"   [FAIL] Login failed: {response.status_code}")

print("\n" + "="*60)
print("SESSION TRACKING TEST COMPLETE")
print("="*60)
