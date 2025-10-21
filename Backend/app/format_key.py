# format_key.py

# IMPORTANT: Change this to the actual path of your .pem file
key_file_path = '/Users/bharat/final_recruiter_keys/public.pem'

try:
    with open(key_file_path, 'r') as f:
        key_content = f.read()

    # repr() automatically adds quotes and escapes newlines perfectly
    formatted_key = repr(key_content)

    print("\nCopy the entire line below into your .env file:\n")
    print(f'JWT_PRIVATE_KEY={formatted_key}')
    print("\n")

except FileNotFoundError:
    print(f"Error: The file '{key_file_path}' was not found.")
    print("Please update the key_file_path variable with the correct path.")