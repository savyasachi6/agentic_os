# ADR 002: Minimal API over Controllers

## Context

ASP.NET Core offers both MVC Controllers and Minimal APIs for building HTTP endpoints. The tools node requires extremely fast startup times, low overhead, and a tiny memory footprint as it operates as a Sidecar to a Python application.

## Decision

We chose to build the node using **ASP.NET Core Minimal APIs**.

## Rationale

- **Ceremony**: Minimal APIs reduce ceremony and boilerplate setup, perfectly matching the micro-API requirement.
- **Performance**: Startup time and memory characteristics are generally better for minimal approaches.
- **Simplicity**: Routes can be grouped efficiently into static classes (`MapShellEndpoints`, `MapFileEndpoints`), while Controllers are better suited for large, monolith HTTP API layers with complex MVC routing.
