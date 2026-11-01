#include "ShowcaseEditor.h"
#include "Modules/ModuleManager.h"
#include "Editor.h"
#include "Landscape.h"
#include "LandscapeComponent.h"
#include "Misc/FileHelper.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "PhysicsEngine/BodySetup.h"
#include "Lightmass/LightmassImportanceVolume.h"
#include "Builders/CubeBuilder.h"
#include "Engine/Polys.h"
#include "Model.h"
#include "Components/BrushComponent.h"
#include "Editor/UnrealEdTypes.h"
#include "Engine/Level.h"
#include "Engine/MapBuildDataRegistry.h"
#include "Misc/App.h"
#include "UObject/Package.h"
IMPLEMENT_MODULE(FDefaultModuleImpl,AeronautTools)
ALandscape* UShowcaseEditor::ImportLandscape(const FString& HeightFile,UMaterialInterface* Material) {
    TArray<uint8> Bytes;
    if(!FFileHelper::LoadFileToArray(Bytes,*HeightFile) || Bytes.Num()!=1009*1009*2) { UE_LOG(LogTemp,Error,TEXT("Invalid 1009-square heightfield: %s"),*HeightFile); return nullptr; }
    UWorld* World=GEditor->GetEditorWorldContext().World();
    if(!World) return nullptr;
    ALandscape* Land=World->SpawnActor<ALandscape>();
    Land->SetActorLabel(TEXT("North Coast - sculptable landscape"));
    Land->SetActorLocation(FVector(-151200,-151200,0));
    Land->SetActorScale3D(FVector(300,300,256));
    Land->LandscapeMaterial=Material;
    Land->StaticLightingResolution=1;
    TMap<FGuid,TArray<uint16>> Heights;
    TArray<uint16>& Data=Heights.Add(FGuid()); Data.SetNumUninitialized(1009*1009);
    FMemory::Memcpy(Data.GetData(),Bytes.GetData(),Bytes.Num());
    TMap<FGuid,TArray<FLandscapeImportLayerInfo>> Layers; Layers.Add(FGuid());
    Land->Import(FGuid::NewGuid(),0,0,1008,1008,1,63,Heights,*HeightFile,Layers,ELandscapeImportAlphamapType::Additive,TArrayView<const FLandscapeLayer>());
    Land->CreateLandscapeInfo(); Land->PostEditChange(); Land->MarkPackageDirty();
    return Land;
}
void UShowcaseEditor::ConfigureMesh(UStaticMesh* Mesh,bool Collision,bool Foliage) {
    if(!Mesh) return;
    const FString Name=Mesh->GetName();
    const bool Small=Name==TEXT("Fence") || Name==TEXT("Cone") || Name==TEXT("RunwayLight") || Name==TEXT("Marking");
    Mesh->SetLightMapCoordinateIndex(1); Mesh->SetLightMapResolution(Name==TEXT("GrassClump")?16:Small?32:Foliage?16:128);
    FStaticMeshSourceModel& Base=Mesh->GetSourceModel(0);
    Base.BuildSettings.bGenerateLightmapUVs=true; Base.BuildSettings.SrcLightmapIndex=0; Base.BuildSettings.DstLightmapIndex=1;
    Base.BuildSettings.bRecomputeNormals=false; Base.BuildSettings.bRecomputeTangents=true;
    const FMeshBuildSettings BuildSettings=Base.BuildSettings;
    if(Mesh->GetNumSourceModels()==1) {
        for(int L=1;L<3;++L) {
            FStaticMeshSourceModel& Lod=Mesh->AddSourceModel();
            Lod.ReductionSettings.PercentTriangles=L==1?.40f:.12f;
            Lod.ReductionSettings.BaseLODModel=0;
            Lod.BuildSettings=BuildSettings;
        }
    }
    if(Collision) { Mesh->CreateBodySetup(); Mesh->GetBodySetup()->CollisionTraceFlag=CTF_UseComplexAsSimple; }
    Mesh->Build(false); Mesh->PostEditChange(); Mesh->MarkPackageDirty();
}
FVector UShowcaseEditor::MeshDimensions(UStaticMesh* Mesh) { return Mesh?Mesh->GetBounds().BoxExtent*2:FVector::ZeroVector; }
void UShowcaseEditor::ConfigureGeographicMesh(UStaticMesh* Mesh,bool Collision,bool Foliage,bool PreserveGeometry) {
    if(!Mesh || Mesh->GetNumSourceModels()<1) return;
    // Geographic shoreline/roof triangles are already bounded authored batches.
    // Reducing them can open courtyards, sever islands or remove low roofs.
    Mesh->SetNumSourceModels(1);
    auto& Base=Mesh->GetSourceModel(0);
    Base.BuildSettings.bGenerateLightmapUVs=false;
    Base.BuildSettings.bRecomputeNormals=false;
    Base.BuildSettings.bRecomputeTangents=true;
    Mesh->GetNaniteSettings().bEnabled=false;
    const FMeshBuildSettings Settings=Base.BuildSettings;
    if(!PreserveGeometry) {
        for(int L=1;L<3;++L) {
            auto& Lod=Mesh->AddSourceModel();
            Lod.BuildSettings=Settings;
            Lod.ReductionSettings.PercentTriangles=L==1?.65f:.35f;
            Lod.ReductionSettings.BaseLODModel=0;
        }
    }
    if(Collision) { Mesh->CreateBodySetup(); Mesh->GetBodySetup()->CollisionTraceFlag=CTF_UseComplexAsSimple; }
    Mesh->Build(false); Mesh->PostEditChange(); Mesh->MarkPackageDirty();
}
void UShowcaseEditor::BuildReflections() {
    GEditor->BuildReflectionCaptures();
    UE_LOG(LogTemp,Display,TEXT("AERONAUT_REFLECTIONS_BUILT"));
}
bool UShowcaseEditor::AttachDetailBuildData(UObject* BuildData) {
    if(FApp::CanEverRender()) return false;
    UWorld* World=GEditor->GetEditorWorldContext().World();
    auto* Registry=Cast<UMapBuildDataRegistry>(BuildData);
    if(!World || !World->PersistentLevel || !Registry ||
       World->GetPathName()!=TEXT("/Game/KeyWestDetail/KeyWestDetail.KeyWestDetail") ||
       Registry->GetPathName()!=TEXT("/Game/KeyWestDetail/KeyWestDetail_BuiltData.KeyWestDetail_BuiltData")) return false;
    ULevel* Level=World->PersistentLevel;
    // Never replace live/shared rendering resources. SaveAs leaves this
    // NonPIEDuplicateTransient pointer null; an existing isolated pointer is OK.
    if(Level->MapBuildData && Level->MapBuildData!=Registry) return false;
    Registry->GetOutermost()->SetPackageFlags(PKG_ContainsMapData);
    Registry->SetFlags(RF_Public|RF_Standalone);
    Registry->MarkPackageDirty();
    if(!Level->MapBuildData) {
        Level->MapBuildData=Registry;
        Level->MarkPackageDirty(); World->MarkPackageDirty();
    }
    return true;
}
bool UShowcaseEditor::EnsureEditorPreview() {
    UWorld* World=GEditor->GetEditorWorldContext().World();
    if(!World) return false;
    if(World->EditorViews.IsValidIndex(LVT_Perspective) && !World->EditorViews[LVT_Perspective].CamPosition.IsNearlyZero()) return false;
    World->EditorViews.SetNum(FMath::Max(World->EditorViews.Num(),int32(LVT_MAX)));
    auto& View=World->EditorViews[LVT_Perspective];
    View.CamPosition=FVector(-115000,-90000,55000); View.CamRotation=FRotator(-18,38,0); View.CamUpdated=true;
    World->MarkPackageDirty(); return true;
}
void UShowcaseEditor::AddLightingImportanceVolume() {
    UWorld* World=GEditor->GetEditorWorldContext().World();
    auto* Volume=World->SpawnActor<ALightmassImportanceVolume>();
    Volume->SetActorLabel(TEXT("Baked lighting - complete flight area"));
    Volume->Brush=NewObject<UModel>(Volume,NAME_None,RF_Transactional); Volume->Brush->Initialize(nullptr,true);
    auto* Builder=NewObject<UCubeBuilder>(Volume);
    Builder->X=330000; Builder->Y=330000; Builder->Z=70000;
    Builder->Build(World,Volume); Volume->SetActorLocation(FVector(0,0,30000));
    Volume->GetBrushComponent()->Brush=Volume->Brush;
    Volume->PostEditChange(); Volume->MarkPackageDirty();
}
