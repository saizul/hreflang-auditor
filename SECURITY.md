# Security policy

## Supported versions

Security fixes are released for the latest minor version.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | yes       |

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability
reporting ("Security" tab, "Report a vulnerability") on
<https://github.com/saizul/hreflang-auditor>, or contact the maintainer through
<https://saizul.com>.

Include a description, steps to reproduce and the affected version. You can
expect an acknowledgement within 7 days. Please allow a reasonable time for a fix
before public disclosure.

## Scope and hardening notes

hreflang-auditor fetches and parses content from servers you point it at, so
treat every audited site as untrusted input:

- HTML reports escape every value taken from crawled pages; CSV exports prefix
  cells starting with `=`, `+`, `-`, `@`, tab or carriage return to stop formula
  injection in spreadsheet applications.
- Response bodies are capped (5 MB by default), decompressed sitemaps are capped
  at 60 MB and XML with entity declarations is rejected.
- Only `http` and `https` URLs are fetched. Note that hreflang targets on other
  hosts are fetched by default; use `--same-host` when auditing from a network
  that can reach internal services you do not want contacted.
- `--insecure` disables TLS verification and should only be used for staging
  environments you control.
