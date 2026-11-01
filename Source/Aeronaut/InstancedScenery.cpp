#include "InstancedScenery.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
AInstancedScenery::AInstancedScenery() {
    Instances=CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("SceneryInstances"));
    SetRootComponent(Instances); Instances->SetMobility(EComponentMobility::Static);
    Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Instances->bEnableDensityScaling=true;
}
