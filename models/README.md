# models/ — the interchangeable slot (Module 3)

Every strategy = one class implementing the framework's model interface:

    model = MyModel(MyParams(), execution_tf="5m", bias_tfs=["1h"])
    config = RunConfig(data_files=..., execution_tf="5m", model=model)
    result = run_strategy(config)          # simulation OR live, unchanged

Reference implementations (ported, in framework/):
- ScalpingModel  — market-structure scalping (the original)
- model_cnn      — ReversalCNN wavelet patterns
- template_matcher — pattern template scores

JP's new algorithm lands here as the next model. No engine changes allowed
without a walk-forward A/B against the incumbent + HODL + capital floor.
