mindmap
  root((SimliServiceIssues))
    Summary
      PrimaryRootCause["Pipecat_Simli_API_migration led to missing InputParams; Simli defaults then enforce short idle/session limits, causing ClientInitiated disconnect ~45-60s."]
      SecondaryRootCause["Audio sent before Simli WSDC/WebSocket ready triggers 'WSDC Not ready' spam; readiness gating exists but relies on private attribute."]
      LocalRunnerDrift["botrunner.py still constructs Simli without InputParams, so local testing may still reproduce the timeout even if bot.py is fixed."]

    Symptoms_Observed
      DisconnectAfter1Min["Avatar video disconnects after ~45-60s (sometimes 45-69s)."]
      Log_WSDCNotReady["Repeated: 'Error sending audio: WSDC Not ready, please wait until self.ready is True'."]
      Log_ClientInitiated["Disconnect reason logged as ClientInitiated (Simli side closing)."]
      UserImpact
        VideoStops["Avatar video stream ends; audio may continue or pipeline degrades."]
        GreetingRace["If greeting queued before Simli ready, first seconds can fail/spam logs."]

    Evidence_InRepo
      SESSION_HANDOFF
        HandoffLines["SESSION_HANDOFF.md documents the exact errors, timing, and a prior fix commit message."]
        HypothesisRecorded["Handoff attributes ClientInitiated disconnect to short SDK defaults when InputParams omitted after API migration."]
      bot_py
        InputParamsPresent["bot.py constructs SimliVideoService with InputParams(max_session_length=3600, max_idle_time=300)."]
        ReadyWaitPresent["bot.py waits up to 30s for simli._client.ready before sending first greeting."]
        Note_PrivateAttr["Ready check uses simli._client.ready (private/internal, may change across versions)."]
      botrunner_py
        InputParamsMissing["botrunner.py constructs SimliVideoService(api_key, face_id) with no InputParams, likely reverting to problematic defaults in local runs."]
      Dependencies
        PipecatVersion["pyproject.toml pins pipecat-ai[...simli]>=0.0.99; handoff notes pipecat 0.0.99 in logs."]

    RootCause_Hypotheses_Ranked
      H1_DefaultTimeouts
        WhyLikely["Matches observed 45-60s disconnect and ClientInitiated closure; fixed by explicitly setting max_session_length/max_idle_time."]
        Trigger["Omitting SimliVideoService.InputParams after deprecation of SimliConfig defaults."]
        WhereTriggered
          LocalRuns["Any code path using botrunner.py (or any other constructor without params)."]
          OlderDeployImage["Deploy image built from older bot.py without params, or cached Docker layer still using old code."]
      H2_ReadinessRace
        WhyPossible["Explains 'WSDC Not ready' spam when audio frames arrive before websocket/data-channel is ready."]
        Limits["Does not fully explain consistent ~1 minute disconnect by itself; more of a symptom amplifier."]
        BrittleWorkaround["Polling simli._client.ready works but depends on internals."]
      H3_MisconfigOrAuth
        WhyLessLikely["Would fail immediately (401/403/connection fail) rather than consistently at ~1 minute."]
        StillCheck
          KeysSet["SIMLI_API_KEY and SIMLI_FACE_ID must be present in runtime env/secret set."]
          FaceIdValid["Invalid face id can manifest as early stream termination depending on Simli service behavior."]
      H4_NetworkOrPlatformPolicy
        WhyLessLikely["Would usually show transport errors or varying timing; observed pattern aligns better with idle/session defaults."]
        Examples
          NATIdle["NAT/load-balancer idle timeouts on websocket if no keepalive."]
          CloudEgress["Platform egress constraints or websocket proxy timeouts."]

    ContributingFactors
      MixedEntryPoints["Two entry points (bot.py for Pipecat Cloud, botrunner.py for local) diverge in Simli configuration."]
      HiddenInternalState["Simli readiness exposed only via private fields; higher chance of regressions when upgrading pipecat/simli-ai."]
      ObservabilityGap["Logs capture symptom; add more structured logging around Simli connect/ready/disconnect events for faster future triage."]
      SecretsInRepoRisk["A file named ',env' contains secrets; risk of accidental leakage and confusion about which env file is used."]

    Mitigations_Recommended
      EnsureParamsEverywhere
        Action["Always pass SimliVideoService.InputParams in every SimliVideoService construction path (bot.py and any local runner)."]
        BaselineValues
          max_session_length_3600["max_session_length=3600 (1h) to avoid premature session expiry during calls."]
          max_idle_time_300["max_idle_time=300 (5m) to match prior working defaults per handoff."]
      ReadinessGating
        Keep["Do not send greeting/audio frames until Simli is ready; reduces WSDC spam and improves first-response UX."]
        Improve["Prefer a public 'ready' API/event if/when pipecat exposes it; avoid relying on simli._client internals."]
      KeepaliveIfNeeded
        When["If disconnects persist in certain networks/platforms, consider explicit keepalive/heartbeat frames if Simli supports it."]
      DeploymentHygiene
        RebuildNoCache["Rebuild container with --no-cache to ensure updated bot.py is in the image."]
        VerifyRuntimeVersion["Log pipecat-ai and simli-ai versions at startup to correlate behavior with dependency changes."]
      SecretHygiene
        RemoveSecretsFromGit["Ensure ',env' is not committed; keep secrets only in .env (gitignored) or Pipecat Cloud secret sets."]
        OneSourceOfTruth["Document which file/env vars are actually loaded at runtime to avoid mismatch."]

    Verification_Checklist
      ReproBaseline
        UsingBotrunner["Run via botrunner.py without InputParams should reproduce ~1 minute disconnect (expected if hypothesis H1 is correct)."]
        UsingBotPy["Run via bot.py with InputParams should sustain video past 2-3 minutes and ideally 10+ minutes."]
      RuntimeSignals
        ConfirmNoWSDCSpam["After readiness gating, 'WSDC Not ready' should disappear or be rare (only at startup)."]
        ConfirmNoClientInitiated["No ClientInitiated disconnect near 45-60s."]
        ObserveIdleBehavior["Stay silent >60s; with max_idle_time=300 it should remain connected for at least 5 minutes idle."]
      CloudDeploy
        ImageMatchesSource["Confirm deployed image digest corresponds to rebuilt image containing InputParams."]
        SecretsPresent["Confirm Pipecat Cloud secret set contains SIMLI_API_KEY and SIMLI_FACE_ID."]

    Notes
      Scope["This file documents likely root causes and mitigations based on repo + handoff evidence; it does not run live tests."]
