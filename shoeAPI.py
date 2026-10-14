"""Legacy deployment entry point; business logic lives in shoe_api/."""
import os
from shoe_api import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))
