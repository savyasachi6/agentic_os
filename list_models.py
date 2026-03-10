import urllib.request
import json
req = urllib.request.Request("http://localhost:11434/api/tags")
try:
    with urllib.request.urlopen(req) as response:
        tags = json.loads(response.read())
        print([model['name'] for model in tags.get('models', [])])
except Exception as e:
    print(e)
