#!/bin/bash
docker buildx build --platform linux/amd64 -t trapper137/fast-app:latest --push .