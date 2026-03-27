from tracelet.utils.helper import clean_url_path

test_paths = [
    ("/api/v1/user/123/token/abc-123", "/api/v1/user/<id>/token/<masked>"),
    ("/auth/session_id_here/profile", "/auth/<masked>/profile"),
    ("/login/password/mysecret", "/login/password/<masked>"),
    ("/api/secret/very-secret-key/data", "/api/secret/<masked>/data"),
    ("/api/v1/api_key/secret-key", "/api/v1/api_key/<masked>"),
    ("/api/v1/credentials/user/pass", "/api/v1/credentials/<masked>/pass"),
    ("/path/with/token=somevalue", "/path/with/token=<masked>"),
    ("/api/v1/user/12345678-1234-5678-1234-567812345678/apikey=mykey", "/api/v1/user/<uuid>/apikey=<masked>"),
    ("/sessionid=123/info", "/sessionid=<masked>/info"),
    ("/jwt/encoded.string.here/", "/jwt/<masked>"),
    ("/api/monkey/123", "/api/monkey/<id>"),
    ("/api/oauth/token/123", "/api/oauth/token/<masked>"),
]

all_passed = True
for path, expected in test_paths:
    cleaned = clean_url_path(path)
    if cleaned != expected:
        print(f"FAILED: {path}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {cleaned}")
        all_passed = False
    else:
        print(f"PASSED: {path} -> {cleaned}")

if all_passed:
    print("\nALL SECURITY REPRO CASES PASSED!")
else:
    print("\nSOME CASES FAILED!")
    exit(1)
