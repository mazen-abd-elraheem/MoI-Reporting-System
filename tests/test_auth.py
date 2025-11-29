import requests
import random
import string
import time

# Configuration
BASE_URL = "http://localhost:8080"  # Change to your Azure URL if deploying
# BASE_URL = "https://moi-reporting-api-xyz.azurewebsites.net" 

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_random_email():
    return f"test_{get_random_string()}@moi.gov.eg"

def print_step(step, message):
    print(f"\n[{step}] {'-' * 50}")
    print(f"👉 {message}")

def test_full_flow():
    session = requests.Session()
    password = "password123"
    
    # ==============================================================================
    # STEP 1: REGISTER (Admin Candidate)
    # ==============================================================================
    print_step(1, "Registering Admin Candidate...")
    admin_email = get_random_email()
    
    response = session.post(f"{BASE_URL}/api/v1/auth/register", json={
        "email": admin_email,
        "password": password,
        "role": "admin" # Default registration is always citizen
    })
    
    if response.status_code != 201:
        print(f"❌ Registration Failed: {response.text}")
        return
        
    admin_data = response.json()
    admin_id = admin_data["userId"]
    print(f"✅ Registered: {admin_email} (ID: {admin_id})")

    # ==============================================================================
    # STEP 2: LOGIN (Get Token)
    # ==============================================================================
    print_step(2, "Logging In to get Token...")
    
    # Note: Login endpoint expects Form Data (OAuth2 standard), not JSON
    response = session.post(f"{BASE_URL}/api/v1/auth/login", data={
        "username": admin_email,
        "password": password
    })
    
    if response.status_code != 200:
        print(f"❌ Login Failed: {response.text}")
        return

    token_data = response.json()
    access_token = token_data["access_token"]
    print(f"✅ Login Successful!")
    print(f"🔑 Token: {access_token[:20]}... (truncated)")
    
    # Set Auth header for future requests
    headers = {"Authorization": f"Bearer {access_token}"}

    # ==============================================================================
    # STEP 3: CREATE REPORT (Test Basic Auth)
    # ==============================================================================
    print_step(3, "Submitting a Report (Testing Auth Linkage)...")
    
    # Reports endpoint uses Multipart/Form-Data because of file uploads
    report_data = {
        "title": "Test Incident Report",
        "descriptionText": "This is an automated test report.",
        "categoryId": "infrastructure",
        "location": "30.0444, 31.2357"
    }
    
    response = session.post(
        f"{BASE_URL}/api/v1/reports/", 
        data = report_data, 
        headers = headers # Pass the token here
    )
    
    if response.status_code == 201:
        print(f"✅ Report Created! ID: {response.json()['reportId']}")
    else:
        print(f"❌ Report Creation Failed: {response.text}")

    # ==============================================================================
    # STEP 4: MANUAL INTERVENTION (Database Update)
    # ==============================================================================
    print_step(4, "⚠️  SECURITY CHECKPOINT")
    print(f"To test Role Assignment, user '{admin_email}' MUST be an ADMIN.")
    print("By default, they are just a 'citizen'. The API forbids citizens from assigning roles.")
    print("\n👉 ACTION REQUIRED:")
    print("1. Go to Azure Portal -> SQL Database -> Query Editor (or your local DB tool)")
    print("2. Run this exact SQL command:")
    print(f"\n   UPDATE [dbo].[User] SET role = 'admin' WHERE userId = '{admin_id}';\n")
    
    input(">> Press ENTER once you have run the SQL command to continue...")

    # ==============================================================================
    # STEP 5: TEST ROLE ASSIGNMENT
    # ==============================================================================
    print_step(5, "Testing Role Assignment Endpoint...")
    
    # Create a target user to promote
    target_email = get_random_email()
    print(f"   Creating target user: {target_email}...")
    res_target = requests.post(f"{BASE_URL}/api/v1/auth/register", json={
        "email": target_email, "password": "password123"
    })
    target_id = res_target.json()["userId"]
    
    # Attempt to promote target user to OFFICER
    print(f"   Attempting to promote User {target_id} to OFFICER...")
    
    response = session.put(
        f"{BASE_URL}/api/v1/users/{target_id}/role",
        json={"role": "officer"},
        headers = headers # Using the Admin's token
    )
    
    if response.status_code == 200:
        print("✅ SUCCESS! Role Updated.")
        print(f"   User Response: {response.json()}")
    elif response.status_code == 403:
        print("❌ FAILED (403 Forbidden). Did you run the SQL command in Step 4?")
    else:
        print(f"❌ FAILED: {response.status_code} - {response.text}")

if __name__ == "__main__":
    # Ensure requests is installed
    try:
        import requests
        test_full_flow()
    except ImportError:
        print("Please install 'requests' library first:")
        print("pip install requests")