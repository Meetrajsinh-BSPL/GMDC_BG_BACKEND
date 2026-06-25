#!/bin/sh
set -e

# Rewrite OCI config to point to the in-container key path
if [ -f /tmp/oci-config.src ]; then
    sed "s|^key_file=.*|key_file=/home/appuser/.oci/oci_genai_key.pem|" /tmp/oci-config.src \
        > /home/appuser/.oci/config
    chmod 600 /home/appuser/.oci/config
fi

exec "$@"
