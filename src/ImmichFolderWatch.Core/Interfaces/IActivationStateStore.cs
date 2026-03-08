namespace ImmichFolderWatch.Core.Interfaces;

public interface IActivationStateStore
{
    bool IsInitialVerificationCompleted();

    void MarkInitialVerificationCompleted();
}
