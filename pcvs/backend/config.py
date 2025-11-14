class Config(dict):
    """
    A 'Config' is a dict used to manage all configuration fields.

    While it can contain arbitrary data, the whole PCVS
    configuration is composed of 5 distinct 'categories', each being a single
    Config. These are then gathered in a `MetaConfig` object (see below)
    """

    def __init__(self, d: dict = {}):
        """
        Init the object.

        :param d: items of the configuration
        :type d: dict
        """
        super().__init__(**d)

    @classmethod
    def __to_dict(cls, d):
        for k, v in d.items():
            if isinstance(v, dict):  # is MetaConfig or v is Config:
                d[k] = Config.__to_dict(v)
        return dict(d)

    def to_dict(self):
        """Convert the Config() to regular dict."""
        return Config.__to_dict(self)

    # Additional dict access functions
    def set_ifdef(self, k, v):
        """
        Shortcut function: init self[k] only if v is not None.

        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str
        """
        if v is not None:
            self[k] = v

    def set_nosquash(self, k, v):
        """
        Shortcut function: init self[k] only if v is not already set.

        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str
        """
        if k not in self:
            self[k] = v
