#include "FlightGame.h"
#include "FlightGeometry.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/SceneComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerInput.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "InputCoreTypes.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "CoastalScene.h"
#include "Kismet/GameplayStatics.h"

AFlightGameMode::AFlightGameMode() { DefaultPawnClass=AFlightPawn::StaticClass(); HUDClass=AFlightHUD::StaticClass(); }
void AFlightGameMode::InitGame(const FString& MapName,const FString& Options,FString& ErrorMessage) {
    if(DefaultPawnClass==AFlightPawn::StaticClass() && MapName.EndsWith(TEXT("FlightMap"))) {
      if(UClass* TunedPawn=LoadClass<AFlightPawn>(nullptr,TEXT("/Game/Blueprints/BP_AeronautPawn.BP_AeronautPawn_C"))) {
        DefaultPawnClass=TunedPawn;
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_BLUEPRINT_ACTIVE %s"),*TunedPawn->GetPathName());
    }
    }
    Super::InitGame(MapName,Options,ErrorMessage);
}
AFlightPawn::AFlightPawn() {
    PrimaryActorTick.bCanEverTick=true;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
    Aircraft=CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Aircraft")); Aircraft->SetupAttachment(RootComponent);
    Propeller=CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Propeller")); Propeller->SetupAttachment(Aircraft);
    Camera=CreateDefaultSubobject<UCameraComponent>(TEXT("Camera")); Camera->SetupAttachment(RootComponent);
    Camera->SetFieldOfView(65);
    Camera->PostProcessSettings.bOverride_AutoExposureMethod=true;
    Camera->PostProcessSettings.AutoExposureMethod=AEM_Manual;
    Camera->PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure=true;
    Camera->PostProcessSettings.AutoExposureApplyPhysicalCameraExposure=false;
    Camera->PostProcessSettings.bOverride_AutoExposureBias=true;
    Camera->PostProcessSettings.AutoExposureBias=0;
    AutoPossessPlayer=EAutoReceiveInput::Player0;
}
void AFlightPawn::BeginPlay() {
    Super::BeginPlay();
    CoastalScene=Cast<ACoastalScene>(UGameplayStatics::GetActorOfClass(GetWorld(),ACoastalScene::StaticClass()));
    if(!CoastalScene) BuildWorld();
    BuildAircraft(); ResetFlight(false);
    if(CoastalScene) {
        ApplyShowcasePreset();
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_SHOWCASE_READY Parts=%d TourClearance=%s"),VisualParts.Num(),CoastalScene->ValidateTour()?TEXT("PASS"):TEXT("FAIL"));
        if(FParse::Param(FCommandLine::Get(),TEXT("AeronautAutoTour"))) ToggleGuidedTour();
        if(FParse::Param(FCommandLine::Get(),TEXT("AeronautSelfTest"))) RunShowcaseChecks();
    }
    if(auto* PC=Cast<APlayerController>(GetController())) {
        PC->SetInputMode(FInputModeGameOnly()); PC->bShowMouseCursor=false;
        // Development builds inherit engine view-mode shortcuts on these game keys.
        if(PC->PlayerInput) PC->PlayerInput->DebugExecBindings.RemoveAll([](const FKeyBind& Bind) {
            return Bind.Key==EKeys::F2 || Bind.Key==EKeys::F3 || Bind.Key==EKeys::F4;
        });
    }
}
void AFlightPawn::ResetFlight(bool Free) {
    Flight=FlightSim::State{}; Flight.freeFlight=Free;
    Experience=EFlightExperience::Manual; TourTime=0;
    if(CoastalScene) {
        Flight.freeFlight=true; Flight.position=ACoastalScene::ToSimulation(CoastalScene->AirborneSpawn);
        Flight.previous=Flight.position; Flight.heading=-FMath::DegreesToRadians(CoastalScene->SpawnRotation.Yaw);
    }
    CheckpointToast=0;
    SetActorLocation(FlightGeometry::Position(Flight.position.x,Flight.position.y,Flight.position.z));
    SetActorRotation(FRotator::ZeroRotator); UpdateCamera(1); NotifyCameraCut();
}
void AFlightPawn::NotifyCameraCut() {
    if(auto* PC=Cast<APlayerController>(GetController()))
        if(PC->PlayerCameraManager) PC->PlayerCameraManager->SetGameCameraCutThisFrame();
}
void AFlightPawn::Tick(float Dt) {
    Super::Tick(Dt);
    SmoothedFrameMs=FMath::Lerp(SmoothedFrameMs,Dt*1000.f,1-FMath::Exp(-Dt*2));
    auto* PC=Cast<APlayerController>(GetController()); if(!PC) return;
    using FlightSim::Status;
    auto Press=[&](FKey K) { return PC->WasInputKeyJustPressed(K); };
    auto Down=[&](FKey K) { return PC->IsInputKeyDown(K); };
    auto Axis=[&](FKey K) { const float V=PC->GetInputAnalogKeyState(K); return FMath::Sign(V)*FMath::Max(0.f,(FMath::Abs(V)-.16f)/.84f); };
    if(Press(EKeys::R)) ResetFlight(Flight.freeFlight);
    if(Press(EKeys::One)) ResetFlight(false);
    if(Press(EKeys::Two)) ResetFlight(true);
    if(Press(EKeys::H)) ShowHelp=!ShowHelp;
    if(Press(EKeys::F2)) ShowHUD=!ShowHUD;
    if(CoastalScene && (Press(EKeys::T) || Press(EKeys::Gamepad_Special_Left))) ToggleGuidedTour();
    if(Press(EKeys::F3)) ShowPerformance=!ShowPerformance;
    if(CoastalScene && Press(EKeys::F4)) ApplyShowcasePreset(true);
    if(Press(EKeys::C) || Press(EKeys::Gamepad_FaceButton_Top)) { CameraMode=(CameraMode+1)%3; NotifyCameraCut(); }
    if(Press(EKeys::Gamepad_FaceButton_Left) && Flight.status!=Status::Flying) ResetFlight(!Flight.freeFlight);
    if(Press(EKeys::Enter) || Press(EKeys::SpaceBar) || Press(EKeys::Gamepad_FaceButton_Bottom)) {
        if(Flight.status==Status::Briefing || Flight.status==Status::Paused) Flight.status=Status::Flying;
        else if(Flight.status==Status::Crashed || Flight.status==Status::Complete) { ResetFlight(Flight.freeFlight); Flight.status=Status::Flying; }
    }
    if(Press(EKeys::P) || Press(EKeys::Escape) || Press(EKeys::Gamepad_Special_Right)) {
        if(Flight.status==Status::Flying) Flight.status=Status::Paused;
        else if(Flight.status==Status::Paused) Flight.status=Status::Flying;
    }
    const bool Streaming=FParse::Param(FCommandLine::Get(),TEXT("AeronautStreaming")) || FParse::Param(FCommandLine::Get(),TEXT("AeronautBenchmark"));
    if(!Streaming && !FApp::HasFocus() && Flight.status==Status::Flying) Flight.status=Status::Paused;
    FlightSim::Input Input;
    Input.pitch=double(Down(EKeys::S)||Down(EKeys::Down))-double(Down(EKeys::W)||Down(EKeys::Up));
    Input.roll=double(Down(EKeys::D)||Down(EKeys::Right))-double(Down(EKeys::A)||Down(EKeys::Left));
    Input.yaw=double(Down(EKeys::Q))-double(Down(EKeys::E));
    Input.throttle=double(Down(EKeys::LeftShift)||Down(EKeys::RightShift))-double(Down(EKeys::LeftControl)||Down(EKeys::RightControl));
    Input.pitch=FMath::Clamp((Input.pitch-Axis(EKeys::Gamepad_LeftY))*PitchSensitivity,-1.0,1.0);
    Input.roll=FMath::Clamp((Input.roll+Axis(EKeys::Gamepad_LeftX))*BankSensitivity,-1.0,1.0);
    Input.yaw+=double(Down(EKeys::Gamepad_LeftShoulder))-double(Down(EKeys::Gamepad_RightShoulder));
    Input.throttle+=PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis)-PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis);
    const int PreviousCheckpoint=Flight.checkpoint;
    LastInput=Input;
    // Fixed-size substeps preserve game speed at 20-30 FPS; discard long hitch time.
    double Remaining=FMath::Min(double(Dt),.25);
    if(CoastalScene && Experience==EFlightExperience::GuidedTour) UpdateGuidedTour(Dt);
    else while(Remaining>1e-7) {
        const double Step=FMath::Min(Remaining,1.0/120.0);
        if(CoastalScene) FlightSim::Step(Flight,Input,Step,[&](const FlightSim::State& A,const FlightSim::State& B){return CoastalScene->Collides(A,B,this);});
        else FlightSim::Step(Flight,Input,Step);
        Remaining-=Step;
    }
    CheckpointToast=FMath::Max(0.f,CheckpointToast-Dt);
    if(Flight.checkpoint>PreviousCheckpoint) { CheckpointToast=3.f; OnCheckpointPassed(Flight.checkpoint,Flight.score); }
    SetActorLocation(FlightGeometry::Position(Flight.position.x,Flight.position.y,Flight.position.z));
    SetActorRotation(FRotator(FMath::RadiansToDegrees(Flight.pitch),-FMath::RadiansToDegrees(Flight.heading),0));
    Aircraft->SetRelativeRotation(FRotator(0,0,-FMath::RadiansToDegrees(Flight.roll)));
    if(Flight.status==Status::Flying || Flight.status==Status::Briefing) PropAngle+=Dt*(1700+Flight.throttle*3600);
    Propeller->SetRelativeRotation(FRotator(0,0,PropAngle));
    if(CoastalScene) UpdateRealisticAircraft();
    for(int J=0;J<Rings.Num();++J) { Rings[J]->SetVisibility(!Flight.freeFlight && J>=Flight.checkpoint && J<=Flight.checkpoint+1); }
    UpdateCamera(Dt);
    if(CoastalScene) UpdateBenchmark(Dt);
}
void AFlightPawn::UpdateCamera(float Dt) {
    const FVector Offset=CameraMode==0?FVector(-ChaseDistance,CoastalScene?180:360,CoastalScene?430:850):CameraMode==1?(CoastalScene?CockpitAnchor:FVector(170,0,130)):(CoastalScene?WingAnchor:FVector(-500,2500,500));
    FTransform CameraFrame=GetActorTransform();
    // Keep the coastal chase horizon stable during the ridge climb.
    if(CoastalScene && CameraMode==0) CameraFrame.SetRotation(FRotator(0,GetActorRotation().Yaw,0).Quaternion());
    const FVector Desired=CameraFrame.TransformPosition(Offset);
    const FVector Target=CameraFrame.TransformPosition(CameraMode==1 && CoastalScene?CockpitAnchor+FVector(15000,0,0):FVector(CameraMode==1?15000:1800,0,CoastalScene?80:150));
    Camera->SetWorldLocation(FMath::VInterpTo(Camera->GetComponentLocation(),Desired,Dt,5));
    Camera->SetWorldRotation((Target-Camera->GetComponentLocation()).Rotation());
    if(CoastalScene && CameraMode==1) {
        Camera->SetWorldLocation(Aircraft->GetComponentTransform().TransformPosition(CockpitAnchor));
        Camera->SetWorldRotation(Aircraft->GetComponentQuat()*FRotator(CockpitLookPitch,0,0).Quaternion());
    }
    if(CoastalScene) Camera->SetFieldOfView(CameraMode==1?78:68);
    Aircraft->SetVisibility(CoastalScene || CameraMode!=1,true);
}


