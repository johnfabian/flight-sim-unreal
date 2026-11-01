#include "FlightGame.h"
#include "FlightGeometry.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"

void AFlightHUD::DrawHUD() {
    Super::DrawHUD();
    auto* Pawn=Cast<AFlightPawn>(GetOwningPawn()); if(!Pawn || !Canvas) return;
    if(!Pawn->ShowHUD) return;
    if(Pawn->CoastalScene) { DrawCoastalHUD(Pawn); return; }
    const auto& S=Pawn->Flight; using FlightSim::Status;
    // Lay out in a 1280 x 720 safe area, independent of browser/window size.
    const float Scale=FMath::Min(Canvas->SizeX/1280.f,Canvas->SizeY/720.f);
    const float Ox=(Canvas->SizeX-1280*Scale)/2,Oy=(Canvas->SizeY-720*Scale)/2;
    const FLinearColor Ink(.92f,.96f,.91f),Gold(1.f,.65f,.30f),Muted(.60f,.76f,.75f),Panel(.008f,.027f,.034f,.80f);
    auto Box=[&](float X,float Y,float W,float H,FLinearColor C) { DrawRect(C,Ox+X*Scale,Oy+Y*Scale,W*Scale,H*Scale); };
    auto Text=[&](const FString& T,float X,float Y,float Size,FLinearColor C) { DrawText(T,C,Ox+X*Scale,Oy+Y*Scale,GEngine->GetMediumFont(),Size*Scale,false); };
    auto Line=[&](float X,float Y,float X2,float Y2,FLinearColor C,float Thick=1.f) { DrawLine(Ox+X*Scale,Oy+Y*Scale,Ox+X2*Scale,Oy+Y2*Scale,C,Thick*Scale); };
    Box(30,28,260,78,Panel); Box(30,28,3,78,Gold);
    Text(TEXT("A E R O N A U T"),48,37,1.35f,Ink);
    Text(TEXT("P E L A G O S   A R C H I P E L A G O"),49,70,.57f,Muted);
    Text(S.freeFlight?TEXT("EXPLORE AT YOUR OWN PACE"):FString::Printf(TEXT("ISLAND EXPEDITION   /   %02d OF 08"),S.checkpoint),49,88,.62f,Gold);
    Box(1052,28,198,78,Panel);
    Text(FString::Printf(TEXT("%05d"),S.score),1070,35,1.6f,Ink);
    Text(FString::Printf(TEXT("POINTS     /     %02d:%02d"),int(S.elapsed)/60,int(S.elapsed)%60),1071,76,.7f,Muted);
    const float Heading=FMath::Fmod(float(-S.heading*180/PI)+36000,360);
    Box(498,28,284,50,Panel);
    for(int J=-4;J<=4;++J) {
        const float X=640+J*29;
        Line(X,58,X,64,J==0?Gold:Muted);
        const int Degree=(FMath::RoundToInt(Heading/10)*10+J*10+360)%360;
        const FString Mark=Degree==0?TEXT("N"):Degree==90?TEXT("E"):Degree==180?TEXT("S"):Degree==270?TEXT("W"):FString::Printf(TEXT("%02d"),Degree/10);
        Text(Mark,X-7,36,.65f,J==0?Gold:Muted);
    }
    Line(636,70,640,65,Gold,2); Line(640,65,644,70,Gold,2);

    if(!S.freeFlight && S.checkpoint<8) {
        const auto& Gate=FlightSim::Gates[S.checkpoint];
        const double Distance=std::hypot(S.position.x-Gate.x,S.position.z-Gate.z);
        Text(FString::Printf(TEXT("%02d   %s"),S.checkpoint+1,UTF8_TO_TCHAR(Gate.name)),47,122,.95f,Ink);
        Text(FString::Printf(TEXT("%.2f KM TO CHECKPOINT"),Distance/1000),48,146,.63f,Gold);
        for(int J=0;J<8;++J) Box(48+J*27,169,20,3,J<S.checkpoint?Ink:J==S.checkpoint?Gold:FLinearColor(.2f,.35f,.35f,.7f));
        FVector2D Screen;
        if(S.status==Status::Flying && GetOwningPlayerController()->ProjectWorldLocationToScreen(FlightGeometry::Position(Gate.x,Gate.y,Gate.z),Screen)) {
            const float X=(Screen.X-Ox)/Scale,Y=(Screen.Y-Oy)/Scale;
            if(X>330 && X<1000 && Y>100 && Y<550) Text(FString::Printf(TEXT("%02d  /  %.1f KM"),S.checkpoint+1,Distance/1000),X-36,Y-45,.65f,Gold);
        }
    }
    Box(30,622,1220,69,Panel);
    auto Instrument=[&](float X,const TCHAR* Caption,const FString& Value,const TCHAR* Unit) {
        Text(Caption,X,631,.59f,Muted); Text(Value,X,648,1.4f,Ink); Text(Unit,X+91,659,.63f,Gold);
    };
    Instrument(49,TEXT("AIRSPEED"),FString::Printf(TEXT("%03.0f"),S.speed*1.94384),TEXT("KTS"));
    Instrument(232,TEXT("ALTITUDE"),FString::Printf(TEXT("%04.0f"),S.position.y*3.28084),TEXT("FT"));
    Instrument(422,TEXT("POWER"),FString::Printf(TEXT("%02.0f"),S.throttle*100),TEXT("%"));
    Box(422,683,120,2,Muted); Box(422,683,120*S.throttle,2,Gold);
    Instrument(602,TEXT("VERTICAL SPEED"),FString::Printf(TEXT("%+.0f"),S.verticalSpeed*196.85),TEXT("FT/M"));
    Instrument(820,TEXT("HEADING"),FString::Printf(TEXT("%03.0f"),Heading),TEXT("DEG"));
    Text(TEXT("C / Y   CAMERA"),1051,635,.7f,Ink);
    Text(TEXT("P / MENU   PAUSE"),1051,658,.65f,Muted);
    Text(TEXT("H  CONTROLS    F3  PERFORMANCE"),33,700,.54f,Muted);
    if(Pawn->ShowPerformance) Text(FString::Printf(TEXT("%.0f FPS  /  %.1f ms  /  DX11"),1000.f/FMath::Max(Pawn->SmoothedFrameMs,.01f),Pawn->SmoothedFrameMs),980,700,.61f,Gold);
    if(Pawn->ShowHelp) {
        Box(30,520,610,88,Panel);
        Text(TEXT("KEYBOARD   S/W pitch   A/D bank   Q/E rudder   Shift/Ctrl power"),46,532,.68f,Ink);
        Text(TEXT("CONTROLLER   Left stick fly   Bumpers rudder   RT/LT power"),46,555,.68f,Ink);
        Text(TEXT("1 expedition   2 explore   R reset   H hide   Alt+F4 quit"),46,578,.65f,Muted);
    }
    if(Pawn->CheckpointToast>0) {
        Box(460,120,360,62,Panel);
        Text(TEXT("CHECKPOINT CLEARED"),480,131,1.05f,Gold);
        Text(FString::Printf(TEXT("%d / 8    KEEP YOUR WINGS LEVEL"),S.checkpoint),481,159,.65f,Ink);
    }
    if(S.stall) { Box(470,540,340,40,Panel); Text(TEXT("STALL  /  INCREASE POWER"),490,550,.9f,Gold); }
    if(S.status!=Status::Flying) {
        Box(30,226,460,252,Panel); Box(30,226,460,3,Gold);
        FString Title=TEXT("Find your horizon.");
        FString Sub=TEXT("Eight checkpoints. Six islands. An open sky.");
        FString Prompt=TEXT("ENTER / A    TAKE FLIGHT");
        if(S.status==Status::Paused) { Title=TEXT("Take a breath."); Sub=TEXT("Your flight is waiting right here."); Prompt=TEXT("ENTER / A    RESUME FLIGHT"); }
        if(S.status==Status::Crashed) { Title=TEXT("Another adventure."); Sub=TEXT("Flight ended. Clear the terrain and keep climbing."); Prompt=TEXT("ENTER / A    TRY AGAIN"); }
        if(S.status==Status::Complete) { Title=TEXT("A journey well flown."); Sub=FString::Printf(TEXT("All eight checkpoints. %d points earned."),S.score); Prompt=TEXT("ENTER / A    FLY AGAIN"); }
        Text(TEXT("W E L C O M E   T O   P E L A G O S"),55,250,.63f,Gold);
        Text(Title,54,284,1.75f,Ink);
        Text(Sub,56,332,.73f,Muted);
        Text(S.freeFlight?TEXT("EXPLORE   /   NO CHECKPOINTS"):TEXT("EXPEDITION   /   FOLLOW THE GOLDEN RINGS"),56,367,.66f,Gold);
        Text(TEXT("1 Expedition    2 Explore    X switch mode    H controls"),56,393,.62f,Muted);
        Line(55,421,465,421,FLinearColor(.3f,.45f,.43f,.6f));
        Text(Prompt,56,438,.98f,Ink);
    }
}
