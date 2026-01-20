#!/bin/bash

export GOOGLE_APPLICATION_CREDENTIALS="/home/ubuntu/projects/banana-slides/tang-vertex.json"
cd backend
uv run python app.py
