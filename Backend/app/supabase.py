# In file: Backend/app/supabase.py

import os
from supabase import create_client, Client
# from dotenv import load_dotenv  <- You can remove this line

# load_dotenv() <- And this line

# os.environ.get() will now work because Docker provides the variables
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# This creates the client instance
supabase_client: Client = create_client(url, key)