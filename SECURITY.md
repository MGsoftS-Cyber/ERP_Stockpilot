# Security configuration

Default Compose is a local development environment. Before an internet deployment,
configure HTTPS, explicit origins/hosts, private AI networking, unique database and
service credentials, a strong Django secret, DEBUG=false and OIDC authentication.
Set `STOCKPILOT_PRODUCTION=true` in the backend environment to activate the
existing startup safeguards. Back up the database, uploaded documents and signing
keys, and test restore in an isolated environment.

Organization roles are enforced by the API, not just by visible buttons. Platform
reviewer staff access exposes publishers' pending submissions and should be granted
only to trusted operators. Uploaded extension packages are declarative JSON; do
not add dynamic imports or arbitrary code execution to the manifest path.

If reporting a security issue, avoid posting credentials or private records in a
public issue. Use GitHub private vulnerability reporting if the repository owner
has enabled it; otherwise request a private reporting channel from the owner.
No security contact or disclosure service has been invented in this package.
