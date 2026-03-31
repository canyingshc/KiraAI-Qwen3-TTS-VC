import requests

API_KEY = "sk-" #这里放入密钥
MIME_TYPE = "audio/mpeg"
BASE64_STR = "这里填入base64编码好的音频"


def get_voice_key():

    data_uri = "data:" + MIME_TYPE + ";base64," + BASE64_STR

    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"

    audio_dict = {}
    audio_dict["data"] = data_uri

    input_dict = {}
    input_dict["action"] = "create"
    input_dict["target_model"] = "qwen3-tts-vc-realtime-2026-01-15" #自定义模型，带vc模型的才支持声音复刻
    input_dict["preferred_name"] = "自定义名称"
    input_dict["audio"] = audio_dict

    payload = {}
    payload["model"] = "qwen-voice-enrollment"
    payload["input"] = input_dict

    headers = {}
    headers["Authorization"] = "Bearer " + API_KEY
    headers["Content-Type"] = "application/json"

    print("uploading...")
    resp = requests.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        print("failed! code: " + str(resp.status_code))
        print(resp.text)
        return None

    result = resp.json()
    print("success!")
    print(result)

    try:
        voice_key = result["output"]["voice"]
        print("voice key: " + voice_key)
        return voice_key
    except KeyError:
        print("no voice key found in response")
        return None


if __name__ == "__main__":
    get_voice_key()