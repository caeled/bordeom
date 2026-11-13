@echo off
rem Everyday Cool Library App - home-server proxy for the web edition.
rem Fetches book files server-side so Gutenberg, Internet Archive and
rem Standard Ebooks read natively in the web page. Leave this window
rem open while you use the web edition. Ctrl+C stops it.
title Everyday Cool Library Proxy
python library-proxy.py
pause
