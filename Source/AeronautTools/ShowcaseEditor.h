#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "ShowcaseEditor.generated.h"
class ALandscape;
class UMaterialInterface;
class UStaticMesh;
UCLASS()
class AERONAUTTOOLS_API UShowcaseEditor : public UBlueprintFunctionLibrary {
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor")
    static ALandscape* ImportLandscape(const FString& HeightFile,UMaterialInterface* Material);
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor")
    static void ConfigureMesh(UStaticMesh* Mesh,bool Collision,bool Foliage);
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor")
    static void ConfigureGeographicMesh(UStaticMesh* Mesh,bool Collision,bool Foliage,bool PreserveGeometry);
    UFUNCTION(BlueprintPure,Category="Showcase|Editor") static FVector MeshDimensions(UStaticMesh* Mesh);
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor") static void AddLightingImportanceVolume();
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor") static bool EnsureEditorPreview();
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor") static void BuildReflections();
    UFUNCTION(BlueprintCallable,Category="Showcase|Editor") static bool AttachDetailBuildData(UObject* BuildData);
};
