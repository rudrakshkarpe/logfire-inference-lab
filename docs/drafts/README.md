# Maintainer review drafts

These files are local drafts. No comment or PR has been submitted from them.

- [Issue follow-up](logfire-2489-follow-up.md): paste-ready text for [pydantic/logfire#2489](https://github.com/pydantic/logfire/issues/2489), “Add a practical guide to observing self-hosted LLM inference.”
- [Guide outline](self-hosted-inference-guide-outline.md): proposed scope for a later documentation PR.

Publish the referenced lab files before posting the follow-up, then replace the draft's `main` links with that commit's permalink. The upstream issue currently has no comments, and its original body already tags a maintainer; this draft adds evidence without another mention.

The GPU run supports the guide proposal. It does not resolve [#2490](https://github.com/pydantic/logfire/issues/2490), which concerns automatic OpenAI instrumentation and exceptions during stream consumption. The real-engine capture uses explicit application spans and tests a pre-generation HTTP error, so it is not a reproduction of that bug.
