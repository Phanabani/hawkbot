import base64
from io import BytesIO
from typing import Optional

import requests

url = "https://api.runwayml.com/v1/inference/runway/AttnGAN/default/generate"
headers = {'content-type': 'application/json'}


def gan_image(text: str) -> Optional[BytesIO]:
    json_data = {'inputData': {'caption': text}}
    # noinspection PyBroadException
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=2)
    except requests.exceptions.ReadTimeout:
        return None
    except Exception:
        return None

    if r.status_code != requests.codes.ok:
        return None

    data_uri = r.json()['result']
    header, encoded = data_uri.split(",", 1)
    return BytesIO(base64.b64decode(encoded))


if __name__ == '__main__':
    with open(r'C:\Users\Alex\Desktop\test.jpg', 'wb') as f:
        f.write(gan_image('A man').read())
