class Storage: ...
class FileSystemStorage(Storage): ...
class DefaultStorage(Storage): ...

default_storage: DefaultStorage = ...
