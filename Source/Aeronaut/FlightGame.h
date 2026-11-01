#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/HUD.h"
#include "FlightSimulation.h"
#include "FlightGame.generated.h"
class UProceduralMeshComponent;
class UCameraComponent;
class UMaterialInterface;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class ACoastalScene;
class FShowcaseResolutionProbe;
UENUM(BlueprintType)
enum class EFlightExperience : uint8 { Manual,GuidedTour };
USTRUCT(BlueprintType)
struct FFlightTelemetry {
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) float AirspeedKnots=0;
    UPROPERTY(BlueprintReadOnly) float AltitudeFeet=0;
    UPROPERTY(BlueprintReadOnly) float HeadingDegrees=0;
    UPROPERTY(BlueprintReadOnly) float PitchDegrees=0;
    UPROPERTY(BlueprintReadOnly) float BankDegrees=0;
    UPROPERTY(BlueprintReadOnly) float VerticalFeetPerMinute=0;
    UPROPERTY(BlueprintReadOnly) float PowerPercent=0;
    UPROPERTY(BlueprintReadOnly) float DerivedEngineRPM=0;
};

UCLASS(Blueprintable)
class AERONAUT_API AFlightPawn : public APawn {
    GENERATED_BODY()
public:
    AFlightPawn();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    FlightSim::State Flight;
    float SmoothedFrameMs=16.67f;
    int CameraMode=0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aeronaut|HUD") bool ShowHelp=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aeronaut|Handling", meta=(ClampMin="0.25", ClampMax="1.5")) float BankSensitivity=1.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aeronaut|Handling", meta=(ClampMin="0.25", ClampMax="1.5")) float PitchSensitivity=1.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aeronaut|Camera", meta=(ClampMin="1800", ClampMax="6000")) float ChaseDistance=3200.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aeronaut|Aircraft") FLinearColor AccentColor=FLinearColor(.82f,.16f,.045f);
    UFUNCTION(BlueprintCallable, Category="Aeronaut") void ResetFlight(bool Free);
    UFUNCTION(BlueprintImplementableEvent, Category="Aeronaut") void OnCheckpointPassed(int32 Checkpoint, int32 TotalScore);
    UFUNCTION(BlueprintPure,Category="Aeronaut|Telemetry") FFlightTelemetry GetTelemetry() const;
    UFUNCTION(BlueprintCallable,Category="Aeronaut|Showcase") void ToggleGuidedTour();
    UPROPERTY(BlueprintReadOnly,Category="Aeronaut|Showcase") EFlightExperience Experience=EFlightExperience::Manual;
    UPROPERTY(BlueprintReadOnly,Category="Aeronaut|Showcase") ACoastalScene* CoastalScene=nullptr;
    UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Aeronaut|Aircraft") TMap<FName,UStaticMesh*> VisualMeshes;
    UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Aeronaut|Aircraft") TMap<FName,UMaterialInterface*> VisualMaterialOverrides;
    UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Aeronaut|Aircraft") TMap<FName,FVector> VisualPivots;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Aeronaut|Camera") FVector CockpitAnchor=FVector(20,-20,74);
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Aeronaut|Camera") float CockpitLookPitch=-13;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Aeronaut|Camera") FVector WingAnchor=FVector(-180,700,170);
    UPROPERTY(BlueprintReadOnly,Category="Aeronaut|HUD") bool ShowHUD=true;
    UPROPERTY(BlueprintReadOnly,Category="Aeronaut|Showcase") bool PerformancePreset=false;
    double TourTime=0;
    bool ShowPerformance=false;
    float CheckpointToast=0;
private:
    UPROPERTY() UCameraComponent* Camera;
    UPROPERTY() UProceduralMeshComponent* Aircraft;
    UPROPERTY() UProceduralMeshComponent* Propeller;
    UPROPERTY() TArray<UProceduralMeshComponent*> Rings;
    UPROPERTY() UMaterialInterface* Surface;
    double PropAngle=0;
    UPROPERTY() TMap<FName,UStaticMeshComponent*> VisualParts;
    UPROPERTY() UMaterialInstanceDynamic* HorizonMaterial;
    FlightSim::Input LastInput;
    double BenchmarkClock=0;
    double BenchmarkLastWall=0;
    double BenchmarkStartWall=0;
    double BenchmarkWarmupWall=0;
    double BenchmarkMeasuredSimulation=0;
    int32 BenchmarkPendingShot=-1;
    int32 BenchmarkShotSettleFrames=0;
    double BenchmarkShotTourTime=0;
    FTransform BenchmarkShotCamera;
    float BenchmarkShotFOV=68;
    bool BenchmarkFinished=false;
    TArray<float> BenchmarkFrames;
    TSharedPtr<FShowcaseResolutionProbe,ESPMode::ThreadSafe> ResolutionProbe;
    void BuildRealisticAircraft();
    void UpdateRealisticAircraft();
    void UpdateGuidedTour(float Dt);
    void UpdateBenchmark(float Dt);
    void ApplyShowcasePreset(bool Toggle=false);
    void RunShowcaseChecks();
    void BuildWorld();
    void BuildAircraft();
    void UpdateCamera(float Dt);
    void NotifyCameraCut();
};

UCLASS()
class AERONAUT_API AFlightHUD : public AHUD {
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    void DrawCoastalHUD(AFlightPawn* Pawn);
};

UCLASS()
class AERONAUT_API AFlightGameMode : public AGameModeBase {
    GENERATED_BODY()
public:
    AFlightGameMode();
    virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
};
