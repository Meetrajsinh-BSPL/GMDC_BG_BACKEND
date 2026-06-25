import os
import sys
import argparse
import json
import oci
from oci.util import to_dict


DEFAULT_ENDPOINT = "https://inference.generativeai.ap-hyderabad-1.oci.oraclecloud.com"

# You can change these defaults here. Values below come from your input.
DEFAULT_PROMPT = "Hello, what is AI ?."
DEFAULT_COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaaa4u5drq3odvarlvrfueouf6z3vtwi6e2top5wyibhcncymyvvima"
DEFAULT_MODEL_ID = "ocid1.generativeaimodel.oc1.ap-hyderabad-1.amaaaaaask7dceya5vgh63kn7duemcsc7hhitvnduml4ivx5k3hjqdevrpfa"


def make_client(config_path, profile, endpoint):
    config_file = os.path.expanduser(config_path) if config_path else None
    if config_file and not os.path.exists(config_file):
        raise FileNotFoundError(f"OCI config file not found: {config_file}")
    config = oci.config.from_file(config_file, profile) if config_file else oci.config.from_file()
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config=config,
        service_endpoint=endpoint,
        retry_strategy=oci.retry.NoneRetryStrategy(),
        timeout=(10, 240),
    )
    return client


def build_chat_details(prompt, compartment_id, model_id, max_tokens=6000):
    # Create content
    content = oci.generative_ai_inference.models.TextContent()
    content.text = prompt

    message = oci.generative_ai_inference.models.Message()
    message.role = "USER"
    message.content = [content]

    chat_request = oci.generative_ai_inference.models.GenericChatRequest()
    chat_request.api_format = oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
    chat_request.messages = [message]
    chat_request.max_tokens = max_tokens
    chat_request.temperature = 1
    chat_request.frequency_penalty = 0
    chat_request.presence_penalty = 0
    chat_request.top_p = 0.95
    chat_request.top_k = 1

    chat_detail = oci.generative_ai_inference.models.ChatDetails()
    chat_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id=model_id)
    chat_detail.chat_request = chat_request
    chat_detail.compartment_id = compartment_id

    return chat_detail


def main():
    parser = argparse.ArgumentParser(description="Test OCI Generative AI chat API")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="Prompt text to send to the model")
    parser.add_argument("--config", default=r"F:\GMDC\gmdc_bg_api\oci-config\config", help="Path to OCI config file (default: ~/.oci/config)")
    parser.add_argument("--profile", default="DEFAULT", help="OCI config profile name (default: DEFAULT)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Generative AI endpoint")
    parser.add_argument("--compartment-id", default=DEFAULT_COMPARTMENT_ID, help="Compartment OCID with access to Generative AI")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Generative AI model OCID to use for chat")
    args = parser.parse_args()

    try:
        client = make_client(args.config, args.profile, args.endpoint)
    except Exception as e:
        print(f"Failed to create OCI client: {e}", file=sys.stderr)
        sys.exit(2)

    chat_detail = build_chat_details(args.prompt, args.compartment_id, args.model_id)

    try:
        response = client.chat(chat_detail)
    except Exception as exc:
        print("API call failed:", exc, file=sys.stderr)
        sys.exit(3)

    # Try to print a clean JSON representation of the returned data
    try:
        if hasattr(response, "data"):
            print(json.dumps(to_dict(response.data), indent=2))
        else:
            print(json.dumps(to_dict(response), indent=2))
    except Exception:
        # Fallback to simple print
        print(response)


if __name__ == "__main__":
    main()
