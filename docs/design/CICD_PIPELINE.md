# Tory CI/CD pipeline

Every change reaches `develop` through a pull request that must pass the quality gates. A release pull request from `develop` to `main` then builds the immutable image, publishes it to GitHub Container Registry (GHCR) and deploys it to the staging VM over SSH. A smoke test against the live HTTPS URL decides whether the run is green. The CD half is defined in TORY-38 (PR #71) and becomes active once the staging VM and its secrets exist.

```mermaid
flowchart TB
    dev["Feature branch<br/>feat/TORY-n-…"] --> pr["Pull request<br/>into develop"]

    subgraph gates["Quality gates (every PR and push to develop/main)"]
        direction LR
        lint["Lint<br/>ruff check"]
        test["Django PostgreSQL CI<br/>check · migrate · makemigrations --check<br/>tests under coverage ≥ 90%"]
        sec["Security<br/>pip-audit · CodeQL · gitleaks"]
        dock["Docker image<br/>build · compose smoke test<br/>non-root + no-secret checks<br/>full suite in container"]
        docs["Documentation CI<br/>Markdown rules · Mermaid render"]
    end

    pr --> gates
    gates -->|"all green + review"| develop[("develop")]
    develop --> rel["Release PR<br/>develop → main"]
    rel --> gates2["Same gates on the<br/>release PR and on main"]
    gates2 -->|"merge"| main[("main")]

    subgraph cd["CD workflow (on main)"]
        direction TB
        gate["Gate: wait until every check<br/>on the merge commit passed"]
        build["Build image<br/>tag sha-&lt;commit&gt; + latest"]
        ghcr[("GHCR<br/>ghcr.io/…/ay2627s2-cicdp-mikeabat")]
        deploy["Deploy job · staging environment<br/>SSH: copy deploy files, write .env,<br/>pull image, compose up --wait<br/>(migrations run on start)"]
        smoke{"Smoke test over HTTPS<br/>/healthz and /login/"}
        gate --> build --> ghcr --> deploy --> smoke
    end

    main --> cd
    smoke -->|"pass"| live["Run green<br/>staging live"]
    smoke -->|"fail"| rollback["Roll back to previous image<br/>run stays red"]

    tag["Tag v* on a deployed commit"] --> release["Release workflow<br/>GitHub Release + versioned image tag"]
```

| Stage | Workflow | Blocks on |
| --- | --- | --- |
| Lint, tests, coverage, migrations | [Django PostgreSQL CI](../../.github/workflows/django-ci.yml) | a ruff finding, a failing test or system check, a missing migration, or coverage below 90% |
| Security | [Security](../../.github/workflows/security.yml) | a vulnerable pinned dependency, a CodeQL failure, or a secret anywhere in Git history |
| Container | [Docker image](../../.github/workflows/docker-ci.yml) | the image not building or becoming healthy, the app running as root, a secret or `.env`/`.git` in the image, or a test failing inside the container |
| Documentation | [Documentation CI](../../.github/workflows/docs-ci.yml) | a Markdown rule violation or a Mermaid diagram that does not render |
| Deploy | CD, Release (TORY-38) | any check on the merge commit failing, the stack not becoming healthy on the VM, or the HTTPS smoke test failing |

See also the [deployment view](DEPLOYMENT.md) and the [component view](COMPONENTS.md).
