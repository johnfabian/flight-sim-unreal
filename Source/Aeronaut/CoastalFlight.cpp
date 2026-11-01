#include "FlightGame.h"
#include "CoastalScene.h"
#include "FlightGeometry.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SplineComponent.h"
#include "Camera/CameraComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/IConsoleManager.h"
#include "UnrealClient.h"
#include "RHI.h"
#include "EngineUtils.h"
#include "InstancedScenery.h"
#include "ShowcaseResolutionProbe.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"

FFlightTelemetry AFlightPawn::GetTelemetry() const {
    FFlightTelemetry T;
    T.AirspeedKnots=Flight.speed*1.943844; T.AltitudeFeet=Flight.position.y*3.28084;
    T.HeadingDegrees=FMath::Fmod(float(-Flight.heading*180/PI)+36000,360);
    T.PitchDegrees=FMath::RadiansToDegrees(Flight.pitch); T.BankDegrees=FMath::RadiansToDegrees(Flight.roll);
    T.VerticalFeetPerMinute=Flight.verticalSpeed*196.8504; T.PowerPercent=Flight.throttle*100;
    T.DerivedEngineRPM=900+Flight.throttle*1700+Flight.speed*1.2;
    return T;
}
void AFlightPawn::BuildRealisticAircraft() {
    for(const auto& Pair:VisualMeshes) {
        if(!Pair.Value) continue;
        // Keep the imported propeller distinct from the legacy procedural component.
        auto* Part=NewObject<UStaticMeshComponent>(this,FName(*FString::Printf(TEXT("Showcase_%s"),*Pair.Key.ToString())));
        AddInstanceComponent(Part); Part->SetupAttachment(Aircraft); Part->SetMobility(EComponentMobility::Movable);
        Part->SetStaticMesh(Pair.Value); Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        // All flight cameras stay close to this small aircraft. Keep glazing,
        // thin control surfaces and calibrated needles out of mesh reduction.
        Part->SetForcedLodModel(1);
        const auto& Slots=Pair.Value->GetStaticMaterials();
        for(int Slot=0;Slot<Slots.Num();++Slot) {
            if(auto* const* Override=VisualMaterialOverrides.Find(Slots[Slot].MaterialSlotName))
                if(*Override) Part->SetMaterial(Slot,*Override);
        }
        if(const auto* Pivot=VisualPivots.Find(Pair.Key)) Part->SetRelativeLocation(*Pivot);
        Part->RegisterComponent(); Part->SetCastShadow(Pair.Key!=TEXT("CabinGlass")); VisualParts.Add(Pair.Key,Part);
        if(Pair.Key==TEXT("Horizon")) HorizonMaterial=Part->CreateDynamicMaterialInstance(0);
    }
    Camera->SetFieldOfView(68);
    Camera->PostProcessSettings.bOverride_AmbientOcclusionIntensity=true;
    Camera->PostProcessSettings.AmbientOcclusionIntensity=.55f;
    Camera->PostProcessSettings.bOverride_BloomIntensity=true;
    Camera->PostProcessSettings.BloomIntensity=.12f;
    Camera->PostProcessSettings.bOverride_ColorSaturation=true;
    Camera->PostProcessSettings.ColorSaturation=FVector4(.97,.97,.97,1);
    Camera->PostProcessSettings.bOverride_ReflectionMethod=true;
    Camera->PostProcessSettings.ReflectionMethod=EReflectionMethod::ScreenSpace;
    ResolutionProbe=FSceneViewExtensions::NewExtension<FShowcaseResolutionProbe>(GetWorld());
}
void AFlightPawn::ApplyShowcasePreset(bool Toggle) {
    FString Preset;
    FParse::Value(FCommandLine::Get(),TEXT("AeronautPreset="),Preset);
    PerformancePreset=Toggle?!PerformancePreset:Preset.Equals(TEXT("Performance"),ESearchCase::IgnoreCase);
    auto Set=[](const TCHAR* Name,float Value) { if(auto* C=IConsoleManager::Get().FindConsoleVariable(Name)) C->Set(Value,ECVF_SetByCode); };
    Set(TEXT("t.MaxFPS"),30); Set(TEXT("r.ScreenPercentage"),PerformancePreset?85:100);
    Set(TEXT("r.ShadowQuality"),PerformancePreset?2:3); Set(TEXT("r.Shadow.MaxResolution"),1024);
    Set(TEXT("r.Shadow.DistanceScale"),PerformancePreset?.55f:1.f);
    Set(TEXT("r.SSR.Quality"),PerformancePreset?1:2);
    Set(TEXT("r.Water.SingleLayer.Reflection"),PerformancePreset?2:3);
    Set(TEXT("r.Water.SingleLayer.DistanceFieldShadow"),0);
    Set(TEXT("r.Water.SingleLayer.VSMFiltering"),0);
    Set(TEXT("r.Streaming.PoolSize"),1000); Set(TEXT("foliage.DensityScale"),PerformancePreset?.55f:1.f);
    // Saved hardware scalability can lower texture detail independently of our
    // presets. Keep the prepared 2K surfaces available at their intended detail.
    Set(TEXT("r.Streaming.MipBias"),0); Set(TEXT("r.MaxAnisotropy"),PerformancePreset?4:8);
    Set(TEXT("r.Tonemapper.Sharpen"),.25); Set(TEXT("r.MotionBlurQuality"),0);
    Set(TEXT("r.ViewDistanceScale"),PerformancePreset?.8f:1.f);
    for(TActorIterator<AInstancedScenery> It(GetWorld());It;++It) {
        It->Instances->bEnableDensityScaling=It->AllowDensityScaling;
        It->Instances->UpdateDensityScaling();
    }
    UE_LOG(LogTemp,Display,TEXT("AERONAUT_PRESET %s 1280x720 internal=%d%%"),PerformancePreset?TEXT("Performance"):TEXT("Quality"),PerformancePreset?85:100);
    UE_LOG(LogTemp,Display,TEXT("AERONAUT_TEXTURE_QUALITY mip_bias=%.1f anisotropy=%d"),
        IConsoleManager::Get().FindConsoleVariable(TEXT("r.Streaming.MipBias"))->GetFloat(),
        IConsoleManager::Get().FindConsoleVariable(TEXT("r.MaxAnisotropy"))->GetInt());
}
void AFlightPawn::ToggleGuidedTour() {
    if(!CoastalScene) return;
    if(Experience==EFlightExperience::GuidedTour) { ResetFlight(true); return; }
    if(CoastalScene->Tour->GetNumberOfSplinePoints()<3 || CoastalScene->TourDuration<=0 || !CoastalScene->ValidateTour()) {
        UE_LOG(LogTemp,Warning,TEXT("Guided route is invalid or does not clear the terrain.")); return;
    }
    ResetFlight(true); Experience=EFlightExperience::GuidedTour; Flight.status=FlightSim::Status::Flying;
    UpdateGuidedTour(0); SetActorLocation(ACoastalScene::ToWorld(Flight.position)); UpdateCamera(1); NotifyCameraCut();
}
void AFlightPawn::RunShowcaseChecks() {
    const auto SavedFlight=Flight; const auto SavedExperience=Experience; const auto SavedTime=TourTime;
    bool All=true; FString Results=TEXT("{\"checks\":["); int Count=0;
    auto Test=[&](const TCHAR* Name,bool Pass) {
        if(Count++) Results+=TEXT(","); All&=Pass;
        Results+=FString::Printf(TEXT("{\"name\":\"%s\",\"passed\":%s}"),Name,Pass?TEXT("true"):TEXT("false"));
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_CHECK %s %s"),Name,Pass?TEXT("PASS"):TEXT("FAIL"));
    };
    auto StateAt=[](FVector P){FlightSim::State S;S.position=ACoastalScene::ToSimulation(P);S.freeFlight=true;return S;};
    Test(TEXT("Imported aircraft parts"),VisualParts.Num()==26);
    Test(TEXT("Tour terrain clearance"),CoastalScene->ValidateTour());
    Test(TEXT("Scene terrain and collision references"),IsValid(CoastalScene->TerrainActor) && CoastalScene->CollisionSources.Num()>0);
    const auto Spawn=StateAt(CoastalScene->AirborneSpawn);
    Test(TEXT("Safe airborne spawn"),!CoastalScene->Collides(Spawn,Spawn,this));
    const auto Sea=StateAt(FVector(-250000,-250000,50)); Test(TEXT("Water collision"),CoastalScene->Collides(Spawn,Sea,this));
    const auto Bounds=StateAt(FVector(CoastalScene->FlightBounds.X+10000,0,20000)); Test(TEXT("Flight bounds"),CoastalScene->Collides(Spawn,Bounds,this));
    if(CoastalScene->CollisionProbes.Num()>0) {
        for(const auto& Probe:CoastalScene->CollisionProbes) {
            FHitResult Hit; FCollisionQueryParams Query(SCENE_QUERY_STAT(VerifyAuthoredCollision),false,this);
            const bool Direct=GetWorld()->SweepSingleByChannel(Hit,Probe.Start,Probe.End,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(330,60,80)),Query);
            const bool Pass=IsValid(Probe.Target) && CoastalScene->WithinBounds(Probe.Start) && CoastalScene->WithinBounds(Probe.End) && Direct && Hit.GetActor()==Probe.Target && CoastalScene->Collides(StateAt(Probe.Start),StateAt(Probe.End),this);
            Test(*Probe.Name,Pass);
            UE_LOG(LogTemp,Display,TEXT("AERONAUT_COLLISION_TARGET %s expected=%s actual=%s hit=%s"),*Probe.Name,*GetNameSafe(Probe.Target),*GetNameSafe(Hit.GetActor()),*Hit.ImpactPoint.ToString());
        }
        const auto& P=CoastalScene->WingProbe;
        FHitResult FuselageHit,WingHit; FCollisionQueryParams Query(SCENE_QUERY_STAT(VerifyAuthoredWing),false,this);
        const bool FuselageBlocked=GetWorld()->SweepSingleByChannel(FuselageHit,P.Start,P.End,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(330,60,80)),Query);
        const FVector Offset(0,0,135);
        const bool WingBlocked=GetWorld()->SweepSingleByChannel(WingHit,P.Start+Offset,P.End+Offset,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(65,550,14)),Query);
        Test(TEXT("Wing collision while fuselage clear"),IsValid(P.Target) && CoastalScene->WithinBounds(P.Start) && CoastalScene->WithinBounds(P.End) && !FuselageBlocked && WingBlocked && WingHit.GetActor()==P.Target && CoastalScene->Collides(StateAt(P.Start),StateAt(P.End),this));
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_WING_TARGET expected=%s actual=%s fuselage=%s"),*GetNameSafe(P.Target),*GetNameSafe(WingHit.GetActor()),*GetNameSafe(FuselageHit.GetActor()));
    } else {
    const float Ground=CoastalScene->GroundHeight(FVector(10000,20000,0));
    Test(TEXT("Landscape collision"),CoastalScene->Collides(StateAt(FVector(10000,20000,Ground+1000)),StateAt(FVector(10000,20000,Ground-500)),this));
    Test(TEXT("Hangar collision"),CoastalScene->Collides(StateAt(FVector(-60500,-39500,4500)),StateAt(FVector(-60500,-39500,2500)),this));
    bool RockChecked=false;
    for(TActorIterator<AStaticMeshActor> It(GetWorld());It && !RockChecked;++It) {
        auto* Component=It->GetStaticMeshComponent();
        if(!Component->GetStaticMesh() || !Component->GetStaticMesh()->GetName().StartsWith(TEXT("CoastalRock"))) continue;
        FVector Center,Extent; It->GetActorBounds(true,Center,Extent);
        const FVector Start=Center+FVector(0,0,Extent.Z+1000);
        FHitResult RockHit; FCollisionQueryParams RockQuery(SCENE_QUERY_STAT(VerifyCliff),false,this);
        if(GetWorld()->SweepSingleByChannel(RockHit,Start,Center,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeSphere(30),RockQuery) && RockHit.GetActor()==*It)
            RockChecked=CoastalScene->Collides(StateAt(Start),StateAt(Center),this);
    }
    Test(TEXT("Major coastal rock collision"),RockChecked);
    const FVector A(-62000,-38100,2600),B(-60500,-38100,2600); FHitResult Hit; FCollisionQueryParams Query(SCENE_QUERY_STAT(VerifyWing),false,this);
    const bool FuselageBlocked=GetWorld()->SweepSingleByChannel(Hit,A,B,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(330,60,80)),Query);
    Test(TEXT("Wing collision while fuselage clear"),!FuselageBlocked && CoastalScene->Collides(StateAt(A),StateAt(B),this));
    }
    ResetFlight(true); ToggleGuidedTour(); UpdateGuidedTour(CoastalScene->TourDuration-.1f); const double BeforePause=TourTime;
    Flight.status=FlightSim::Status::Paused; UpdateGuidedTour(.5);
    Test(TEXT("Pause freezes guided tour"),TourTime==BeforePause);
    Flight.status=FlightSim::Status::Flying; UpdateGuidedTour(.2f);
    Test(TEXT("Guided tour loop"),TourTime<.2 && Experience==EFlightExperience::GuidedTour);
    ToggleGuidedTour(); Test(TEXT("Tour exit returns safe briefing"),Experience==EFlightExperience::Manual && TourTime==0 && Flight.status==FlightSim::Status::Briefing && Flight.elapsed==0);
    Flight.speed=60; Flight.position.y=100; Flight.heading=-PI/2; Flight.throttle=.7;
    const auto T=GetTelemetry(); Test(TEXT("Live instrument units"),FMath::Abs(T.AirspeedKnots-116.6306)<.01 && FMath::Abs(T.AltitudeFeet-328.084)<.01 && FMath::Abs(T.HeadingDegrees-90)<.01 && T.PowerPercent==70);
    Flight.speed=90/1.943844; Flight.position.y=250/3.28084; Flight.heading=-PI/2; Flight.verticalSpeed=1000/196.8504; Flight.roll=PI/6;
    UpdateRealisticAircraft();
    auto Roll=[&](const TCHAR* Part){return VisualParts.FindChecked(Part)->GetRelativeRotation().Roll;};
    Test(TEXT("Gauge needles match dial calibration"),FMath::Abs(Roll(TEXT("NeedleAirspeed")))<.1 && FMath::Abs(Roll(TEXT("NeedleAltitude"))-90)<.1 && FMath::Abs(Roll(TEXT("NeedleHeading"))-90)<.1 && FMath::Abs(Roll(TEXT("NeedleVerticalSpeed"))-65)<.1 && FMath::Abs(Roll(TEXT("Horizon"))-30)<.1);
    const auto* Dial=VisualParts.FindChecked(TEXT("DialAirspeed")); const auto* Needle=VisualParts.FindChecked(TEXT("NeedleAirspeed"));
    Test(TEXT("Imported gauge and pivot alignment"),FMath::Abs(Dial->GetStaticMesh()->GetBounds().Origin.Y-Needle->GetRelativeLocation().Y)<.1);
    LastInput.pitch=.5; LastInput.roll=1; LastInput.yaw=1; UpdateRealisticAircraft();
    auto Trailing=[&](const TCHAR* Part){return VisualParts.FindChecked(Part)->GetRelativeTransform().TransformVector(FVector(-20,0,0));};
    Test(TEXT("Control surfaces follow pilot commands"),Trailing(TEXT("AileronLeft")).Z<0 && Trailing(TEXT("AileronRight")).Z>0 && Trailing(TEXT("ElevatorLeft")).Z>0 && Trailing(TEXT("Rudder")).Y<0);
    Flight=SavedFlight; Experience=SavedExperience; TourTime=SavedTime;
    Results+=FString::Printf(TEXT("],\"passed\":%s}"),All?TEXT("true"):TEXT("false"));
    const FString Folder=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Benchmarks"),CoastalScene->EvidenceSubdirectory); IFileManager::Get().MakeDirectory(*Folder,true);
    FFileHelper::SaveStringToFile(Results,*FPaths::Combine(Folder,TEXT("ShowcaseChecks.json")));
    if(All) { UE_LOG(LogTemp,Display,TEXT("AERONAUT_SELFTEST_PASS")); }
    else { UE_LOG(LogTemp,Error,TEXT("AERONAUT_SELFTEST_FAILED")); }
}
void AFlightPawn::UpdateGuidedTour(float Dt) {
    if(Flight.status!=FlightSim::Status::Flying || !CoastalScene || CoastalScene->TourDuration<=0) return;
    TourTime=std::fmod(TourTime+Dt,CoastalScene->TourDuration);
    auto* Spline=CoastalScene->Tour; const double Length=Spline->GetSplineLength();
    const double Distance=Length*TourTime/CoastalScene->TourDuration;
    const FVector P=Spline->GetLocationAtDistanceAlongSpline(Distance,ESplineCoordinateSpace::World);
    const FVector Dir=Spline->GetDirectionAtDistanceAlongSpline(Distance,ESplineCoordinateSpace::World);
    const FVector Next=Spline->GetDirectionAtDistanceAlongSpline(FMath::Fmod(Distance+300,Length),ESplineCoordinateSpace::World);
    const double Speed=Length/CoastalScene->TourDuration/100;
    Flight.previous=Flight.position; Flight.position=ACoastalScene::ToSimulation(P);
    Flight.heading=-FMath::DegreesToRadians(Dir.Rotation().Yaw);
    Flight.pitch=FMath::DegreesToRadians(Dir.Rotation().Pitch);
    const double Curvature=FVector::CrossProduct(Dir,Next).Z/3;
    Flight.roll=FMath::Clamp(-std::atan(Curvature*Speed*Speed/9.81),-.5,.5);
    Flight.speed=Speed; Flight.verticalSpeed=Dir.Z*Speed;
    Flight.elapsed+=Dt; Flight.distance+=Speed*Dt; Flight.stall=false;
    LastInput.roll=-Flight.roll*.6; LastInput.pitch=Flight.pitch*.5; LastInput.yaw=0;
}
void AFlightPawn::UpdateRealisticAircraft() {
    auto Rotate=[&](const TCHAR* Name,FRotator R) { if(auto* const* Part=VisualParts.Find(FName(Name))) (*Part)->SetRelativeRotation(R); };
    Rotate(TEXT("Propeller"),FRotator(0,0,PropAngle));
    Rotate(TEXT("AileronLeft"),FRotator(LastInput.roll*13,0,0)); Rotate(TEXT("AileronRight"),FRotator(-LastInput.roll*13,0,0));
    Rotate(TEXT("ElevatorLeft"),FRotator(-LastInput.pitch*12,0,0)); Rotate(TEXT("ElevatorRight"),FRotator(-LastInput.pitch*12,0,0));
    Rotate(TEXT("Rudder"),FRotator(0,LastInput.yaw*15,0));
    Rotate(TEXT("Yoke"),FRotator(0,0,LastInput.roll*32));
    if(auto* const* Part=VisualParts.Find(TEXT("Yoke"))) (*Part)->SetRelativeLocation(VisualPivots[TEXT("Yoke")]+FVector(-LastInput.pitch*3,0,0));
    if(auto* const* Part=VisualParts.Find(TEXT("Throttle"))) (*Part)->SetRelativeLocation(VisualPivots[TEXT("Throttle")]+FVector(Flight.throttle*5,0,0));
    const auto T=GetTelemetry();
    Rotate(TEXT("NeedleAirspeed"),FRotator(0,0,-130+FMath::Clamp(T.AirspeedKnots/180,0.f,1.f)*260));
    Rotate(TEXT("NeedleAltitude"),FRotator(0,0,FMath::Fmod(T.AltitudeFeet/1000*360,360)));
    Rotate(TEXT("NeedleHeading"),FRotator(0,0,T.HeadingDegrees));
    Rotate(TEXT("NeedleVerticalSpeed"),FRotator(0,0,FMath::Clamp(T.VerticalFeetPerMinute/2000,-1.f,1.f)*130));
    Rotate(TEXT("NeedleRPM"),FRotator(0,0,-130+FMath::Clamp(T.DerivedEngineRPM/3000,0.f,1.f)*260));
    Rotate(TEXT("Horizon"),FRotator(0,0,T.BankDegrees));
    if(HorizonMaterial) HorizonMaterial->SetScalarParameterValue(TEXT("Pitch"),T.PitchDegrees/27.f);
}
void AFlightPawn::UpdateBenchmark(float Dt) {
    if(!FParse::Param(FCommandLine::Get(),TEXT("AeronautBenchmark")) || BenchmarkFinished) return;
    const double WallNow=FPlatformTime::Seconds();
    if(BenchmarkLastWall==0) { BenchmarkLastWall=WallNow; BenchmarkStartWall=WallNow; return; }
    const double RawFrameSeconds=WallNow-BenchmarkLastWall;
    BenchmarkLastWall=WallNow;
    const double Before=BenchmarkClock; BenchmarkClock+=Dt;
    if(FParse::Param(FCommandLine::Get(),TEXT("AeronautShots"))) {
        const int ShotCount=CoastalScene->CaptureViews.IsEmpty()?5:CoastalScene->CaptureViews.Num();
        for(int J=0;J<ShotCount;++J) if(Before<5+J*5 && BenchmarkClock>=5+J*5) {
            const double Times[]={0,0,3.5,67,27}; const int Cameras[]={0,1,0,2,0};
            const bool Authored=CoastalScene->CaptureViews.IsValidIndex(J);
            const double ShotTime=Authored?CoastalScene->CaptureViews[J].TourSeconds:Times[J];
            TourTime=ShotTime; CameraMode=Authored?CoastalScene->CaptureViews[J].CameraMode:Cameras[J]; UpdateGuidedTour(0);
            SetActorLocation(ACoastalScene::ToWorld(Flight.position));
            SetActorRotation(FRotator(FMath::RadiansToDegrees(Flight.pitch),-FMath::RadiansToDegrees(Flight.heading),0));
            Aircraft->SetRelativeRotation(FRotator(0,0,-FMath::RadiansToDegrees(Flight.roll)));
            UpdateRealisticAircraft(); UpdateCamera(1);
            if(!Authored && J==0) {
                Camera->SetWorldLocation(GetActorTransform().TransformPosition(FVector(850,-1150,400)));
                Camera->SetWorldRotation((GetActorLocation()+FVector(0,0,60)-Camera->GetComponentLocation()).Rotation());
            }
            if(!Authored && J==3) {
                Camera->SetWorldLocation(FVector(150000,40000,5500));
                Camera->SetWorldRotation((FVector(130000,28000,600)-Camera->GetComponentLocation()).Rotation());
                Camera->SetFieldOfView(55);
            }
            if(Authored) {
                const auto& View=CoastalScene->CaptureViews[J];
                if(View.WorldCamera) {
                    Camera->SetWorldLocation(View.CameraLocation);
                    Camera->SetWorldRotation((View.CameraTarget-View.CameraLocation).Rotation());
                }
                Camera->SetFieldOfView(View.FieldOfView);
            }
            BenchmarkPendingShot=J; BenchmarkShotSettleFrames=6;
            BenchmarkShotTourTime=ShotTime; BenchmarkShotCamera=Camera->GetComponentTransform(); BenchmarkShotFOV=Camera->FieldOfView;
            NotifyCameraCut();
        }
    }
    if(BenchmarkPendingShot>=0) {
        // Teleports invalidate occlusion/TAA history. Hold the authored pose for
        // several rendered frames before readback so hidden terrain cannot leak water.
        TourTime=BenchmarkShotTourTime; UpdateGuidedTour(0);
        SetActorLocation(ACoastalScene::ToWorld(Flight.position));
        SetActorRotation(FRotator(FMath::RadiansToDegrees(Flight.pitch),-FMath::RadiansToDegrees(Flight.heading),0));
        Aircraft->SetRelativeRotation(FRotator(0,0,-FMath::RadiansToDegrees(Flight.roll)));
        UpdateRealisticAircraft(); Camera->SetWorldTransform(BenchmarkShotCamera); Camera->SetFieldOfView(BenchmarkShotFOV);
        if(--BenchmarkShotSettleFrames==0) {
            const int J=BenchmarkPendingShot;
            UE_LOG(LogTemp,Display,TEXT("AERONAUT_CAPTURE_POSE %d settled=6 aircraft=%s camera=%s direction=%s ground=%.1f"),J+1,*GetActorLocation().ToString(),*Camera->GetComponentLocation().ToString(),*Camera->GetForwardVector().ToString(),CoastalScene->GroundHeight(GetActorLocation()));
            const FString Folder=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("ShowcaseCaptures"),CoastalScene->EvidenceSubdirectory);
            IFileManager::Get().MakeDirectory(*Folder,true);
            FScreenshotRequest::RequestScreenshot(FPaths::Combine(Folder,FString::Printf(TEXT("view-%d.png"),J+1)),true,false);
            BenchmarkPendingShot=-1;
        }
    }
    const int ShotCount=CoastalScene->CaptureViews.IsEmpty()?5:CoastalScene->CaptureViews.Num();
    const double WarmupSeconds=FMath::Max(30.0,ShotCount*5.0+5.0);
    if(!FParse::Param(FCommandLine::Get(),TEXT("AeronautCaptureOnly")) && BenchmarkClock>=WarmupSeconds) {
        FString RequestedPreset; FParse::Value(FCommandLine::Get(),TEXT("AeronautPreset="),RequestedPreset);
        const bool ExpectedPerformance=RequestedPreset.Equals(TEXT("Performance"),ESearchCase::IgnoreCase);
        if(Experience!=EFlightExperience::GuidedTour || Flight.status!=FlightSim::Status::Flying || PerformancePreset!=ExpectedPerformance) {
            BenchmarkFinished=true;
            UE_LOG(LogTemp,Error,TEXT("AERONAUT_BENCHMARK_INVALID Guided flight or requested preset interrupted"));
            FPlatformMisc::RequestExit(false); return;
        }
    }
    if(Before<WarmupSeconds && BenchmarkClock>=WarmupSeconds) {
        BenchmarkWarmupWall=WallNow-BenchmarkStartWall;
        TourTime=0; CameraMode=0; UpdateGuidedTour(0);
        SetActorLocation(ACoastalScene::ToWorld(Flight.position));
        SetActorRotation(FRotator(FMath::RadiansToDegrees(Flight.pitch),-FMath::RadiansToDegrees(Flight.heading),0));
        UpdateCamera(1); NotifyCameraCut();
    }
    if(FParse::Param(FCommandLine::Get(),TEXT("AeronautCaptureOnly")) && BenchmarkClock>=WarmupSeconds-1 && BenchmarkPendingShot<0) {
        BenchmarkFinished=true; UE_LOG(LogTemp,Display,TEXT("AERONAUT_CAPTURE_COMPLETE")); FPlatformMisc::RequestExit(false); return;
    }
    // Unreal clamps world DeltaSeconds on long stalls. Record the real wall
    // interval, while the simulation clock ensures two complete route loops.
    const double RequiredTourSeconds=2.0*CoastalScene->TourDuration;
    if(Before>=WarmupSeconds && BenchmarkMeasuredSimulation<RequiredTourSeconds) {
        BenchmarkFrames.Add(RawFrameSeconds*1000);
        BenchmarkMeasuredSimulation+=Dt;
    }
    if(BenchmarkClock<WarmupSeconds+RequiredTourSeconds || BenchmarkMeasuredSimulation<RequiredTourSeconds) return;
    BenchmarkFinished=true;
    const FString Folder=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Benchmarks"),CoastalScene->EvidenceSubdirectory); IFileManager::Get().MakeDirectory(*Folder,true);
    const FString Name=PerformancePreset?TEXT("Performance"):TEXT("Quality");
    FString CSV=TEXT("frame,frame_ms\n"); double Sum=0;
    for(int J=0;J<BenchmarkFrames.Num();++J) { Sum+=BenchmarkFrames[J]; CSV+=FString::Printf(TEXT("%d,%.5f\n"),J,BenchmarkFrames[J]); }
    FFileHelper::SaveStringToFile(CSV,*FPaths::Combine(Folder,Name+TEXT("-frames.csv")));
    BenchmarkFrames.Sort(); const int N=BenchmarkFrames.Num();
    if(N>0) {
        FTextureMemoryStats TextureStats; RHIGetTextureMemoryStats(TextureStats);
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_TEXTURE_MEMORY AllocatedMiB=%.2f"),(TextureStats.StreamingMemorySize+TextureStats.NonStreamingMemorySize)/(1024.0*1024.0));
        const float P95=BenchmarkFrames[FMath::Clamp(int(N*.95),0,N-1)];
        double Slow=0; const int Count=FMath::Max(1,N/100); for(int J=N-Count;J<N;++J) Slow+=BenchmarkFrames[J];
        FString JSON=FString::Printf(TEXT("{\"preset\":\"%s\",\"output\":\"1280x720\",\"internal_percent\":%d,\"warmup_seconds\":%.3f,\"measured_seconds\":%.3f,\"frames\":%d,\"average_fps\":%.3f,\"p95_ms\":%.3f,\"one_percent_low_fps\":%.3f,\"hitches_over_100ms\":%d,\"tour_clearance_pass\":%s"),*Name,PerformancePreset?85:100,WarmupSeconds,Sum/1000,N,N*1000/Sum,P95,Count*1000/Slow,BenchmarkFrames.FilterByPredicate([](float V){return V>100;}).Num(),CoastalScene->ValidateTour()?TEXT("true"):TEXT("false"));
        const FIntPoint Internal=ResolutionProbe.IsValid()?ResolutionProbe->InternalSize():FIntPoint::ZeroValue;
        const FIntPoint Output=ResolutionProbe.IsValid()?ResolutionProbe->OutputSize():FIntPoint::ZeroValue;
        JSON+=FString::Printf(TEXT(",\"internal_resolution\":\"%dx%d\",\"verified_output\":\"%dx%d\",\"measured_simulation_seconds\":%.3f,\"warmup_wall_seconds\":%.3f,\"tour_uninterrupted\":true,\"scene_tour_seconds\":%.6f,\"required_tour_loops\":2}"),Internal.X,Internal.Y,Output.X,Output.Y,BenchmarkMeasuredSimulation,BenchmarkWarmupWall,CoastalScene->TourDuration);
        FFileHelper::SaveStringToFile(JSON,*FPaths::Combine(Folder,Name+TEXT(".json")));
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_BENCHMARK_COMPLETE %s"),*JSON);
    }
    FPlatformMisc::RequestExit(false);
}
