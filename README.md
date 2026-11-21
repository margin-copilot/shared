# Margin Copilot: shared

Margin Copilot shared library: contracts and the security module used by every service.

Part of **Margin Copilot**, a secure multi-agent pricing assistant on Azure, built as a personal learning project.

**Start here:** [margin-copilot/docs](https://github.com/margin-copilot/docs) explains how the whole system works and how the repos fit together.

## What's in it

- `margin_copilot_shared.security.tokens`: the only token check in the project. Entra v2 tokens, RS256, issuer and tenant, `aud` = this service, a required scope, and the calling app (`azp`) on an allow-list. 401 for an untrusted token, 403 for the wrong scope or caller. The `Caller` carries `groups` (Entra group IDs, when the app requests the claim) and `groups_overage` (too many groups for the token: services that filter on groups must fail closed).
- `margin_copilot_shared.security.middleware.AuthMiddleware`: pure ASGI; rejects requests without a valid bearer token and makes the caller available to the request's code through `security.context.current_request()`.
- `margin_copilot_shared.security.obo`: on-behalf-of exchange, authenticated by a federated credential that trusts the service's managed identity (no secrets).
- `margin_copilot_shared.contracts.AgentReply`: what an agent sends back over A2A (`answer`, `refusal`, `citations` like `PP-04 §3.2`, at most 12). Receivers validate it; it rejects unknown fields, malformed citations and answers over 4,000 characters.
- `margin_copilot_shared.contracts.DraftRequest`, `Proposal`, `ProposalError`: the action agent ↔ proposals-api contract. A draft names a product, an optional region, and exactly one of a new price or a percent. It can't carry a tier or a current price: proposals-api reads those itself. Money has two decimals.
- `margin_copilot_shared.testing.issuer.LocalIssuer`: signs tokens locally for tests and `ADAPTERS=fake`. Deployed services never trust it.

How these fit together: [security model](https://github.com/margin-copilot/docs/blob/main/security-model.md).

## Use it

```toml
[project]
dependencies = ["margin-copilot-shared"]

[tool.uv.sources]
margin-copilot-shared = { git = "https://github.com/margin-copilot/shared", tag = "v0.4.0" }
```

## Test

```bash
uv sync
uv run pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
