#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "InstancedScenery.generated.h"
class UHierarchicalInstancedStaticMeshComponent;
UCLASS()
class AERONAUT_API AInstancedScenery : public AActor {
    GENERATED_BODY()
public:
    AInstancedScenery();
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Scenery") bool AllowDensityScaling=true;
    UPROPERTY(VisibleAnywhere,BlueprintReadOnly) UHierarchicalInstancedStaticMeshComponent* Instances;
};
