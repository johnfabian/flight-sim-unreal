#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FlightSimulation.h"
#include "CoastalScene.generated.h"
class USplineComponent;
USTRUCT(BlueprintType)
struct FCoastalCaptureView {
    GENERATED_BODY()
    UPROPERTY(EditAnywhere,BlueprintReadWrite) float TourSeconds=0;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) int32 CameraMode=0;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) bool WorldCamera=false;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FVector CameraLocation=FVector::ZeroVector;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FVector CameraTarget=FVector::ZeroVector;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) float FieldOfView=68;
};
USTRUCT(BlueprintType)
struct FCoastalCollisionProbe {
    GENERATED_BODY()
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FString Name;
    UPROPERTY(EditInstanceOnly,BlueprintReadWrite) AActor* Target=nullptr;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FVector Start=FVector::ZeroVector;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FVector End=FVector::ZeroVector;
};
UCLASS(Blueprintable)
class AERONAUT_API ACoastalScene : public AActor {
    GENERATED_BODY()
public:
    ACoastalScene();
    UPROPERTY(VisibleAnywhere,BlueprintReadOnly) USplineComponent* Tour;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase") FVector AirborneSpawn=FVector(-115000,-55000,18000);
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase") FRotator SpawnRotation=FRotator::ZeroRotator;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase") FVector FlightBounds=FVector(300000,300000,95000);
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase") float TourDuration=150.f;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString RegionLabel=TEXT("NORTH COAST  /  PACIFIC NORTHWEST");
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString BriefingLabel=TEXT("N O R T H   C O A S T   A I R F I E L D");
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString BriefingTitle=TEXT("The coast is calling.");
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString BriefingSubtitle=TEXT("A quiet airfield. An open Pacific horizon.");
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString StartLabel=TEXT("ENTER / A    FLY THE COAST");
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString AttributionLine1;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Presentation") FString AttributionLine2;
    // Empty arrays retain the original North Coast capture/check defaults.
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Evidence") TArray<FCoastalCaptureView> CaptureViews;
    UPROPERTY(EditInstanceOnly,BlueprintReadWrite,Category="Showcase|Evidence") TArray<FCoastalCollisionProbe> CollisionProbes;
    UPROPERTY(EditInstanceOnly,BlueprintReadWrite,Category="Showcase|Evidence") FCoastalCollisionProbe WingProbe;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Showcase|Evidence") FString EvidenceSubdirectory;
    UPROPERTY(EditInstanceOnly,BlueprintReadWrite,Category="Showcase") AActor* TerrainActor=nullptr;
    UPROPERTY(EditInstanceOnly,BlueprintReadWrite,Category="Showcase") TArray<AActor*> CollisionSources;
    UFUNCTION(BlueprintCallable,Category="Showcase") float GroundHeight(FVector Point) const;
    UFUNCTION(BlueprintCallable,Category="Showcase") bool ValidateTour(float MinimumClearance=6000.f) const;
    bool WithinBounds(FVector Point) const;
    bool Collides(const FlightSim::State& Before,const FlightSim::State& After,const AActor* Ignored) const;
    static FVector ToWorld(const FlightSim::Vec& P) { return FVector(-P.z*100,P.x*100,P.y*100); }
    static FlightSim::Vec ToSimulation(FVector P) { return {P.Y/100,P.Z/100,-P.X/100}; }
};
