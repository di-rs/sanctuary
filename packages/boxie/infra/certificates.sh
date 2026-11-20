#!/usr/bin/env bash
# All signing material stays in ca/. Runtime mounts expose only leaf identities.
set -euo pipefail
umask 077
[[ $# == 1 || $# == 3 ]] || exit 2
root=$1
[[ ! -L $root ]] || exit 1
# Columns: identity, issuer, DNS name, usage, UID/GID, then trust roots for the directory.
inventory="$(dirname "$0")/boxie_infra/certificate-identities.conf"
if [[ -d $root ]]; then
    [[ -f $root/complete ]] || { echo 'Partial certificates; restore the complete set.' >&2; exit 1; }
    while read -r identity _; do
        openssl x509 -checkend 604800 -noout -in "$root/$identity.pem" >/dev/null || { echo 'Certificate renewal required.' >&2; exit 1; }
        [[ -s $root/$identity.key ]] || exit 1
    done < "$inventory"
    exit 0
fi
install -d -m 0700 "$(dirname "$root")"
staging=$(mktemp -d "${root}.new.XXXXXX")
trap 'rm -rf "$staging"' EXIT
install -d -m 0700 "$staging/ca"
for name in frontend internode client; do
    openssl req -x509 -newkey rsa:3072 -nodes -days 365 -subj "/CN=Boxie $name CA" \
        -keyout "$staging/ca/$name.key" -out "$staging/ca/$name.pem" >/dev/null 2>&1
done
while read -r identity issuer san usage owner trust_roots; do
    directory="$staging/${identity%/*}"
    name=${identity##*/}
    install -d -m 0755 "$directory"
    for authority in $trust_roots; do
        cp "$staging/ca/$authority.pem" "$directory/$authority-ca.pem"
    done
    openssl req -newkey rsa:2048 -nodes -subj "/CN=$name" -keyout "$staging/$identity.key" -out "$staging/ca/$name.csr" >/dev/null 2>&1
    printf 'subjectAltName=DNS:%s\nextendedKeyUsage=%s\nbasicConstraints=CA:FALSE\n' "$san" "$usage" > "$staging/ca/$name.ext"
    openssl x509 -req -in "$staging/ca/$name.csr" -CA "$staging/ca/$issuer.pem" -CAkey "$staging/ca/$issuer.key" \
        -CAcreateserial -days 90 -extfile "$staging/ca/$name.ext" -out "$staging/$identity.pem" >/dev/null 2>&1
    chown "${2:-$owner}:${3:-$owner}" "$staging/$identity.key"
done < "$inventory"
find "$staging" -name '*.pem' -exec chmod 0644 {} +
# The enclosing directory is traversable for the numeric readers; CA directory is private.
chmod 0755 "$staging"
touch "$staging/complete"
mv "$staging" "$root"
