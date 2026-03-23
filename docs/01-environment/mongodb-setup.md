# MongoDB Setup

## Purpose
This document explains how MongoDB is run locally for this project.

MongoDB is started through Docker Compose from the `infra/` folder.

---

## Current approach
This project uses Docker Compose to run MongoDB locally instead of installing MongoDB directly on the machine.

Reasons:
- isolated project setup
- reproducible environment
- easy startup and shutdown
- easier reset and maintenance

---

## Location
Infrastructure configuration lives in:

`infra/docker-compose.yml`

---

## Start MongoDB
From the `infra/` folder:

```powershell
docker compose up -d