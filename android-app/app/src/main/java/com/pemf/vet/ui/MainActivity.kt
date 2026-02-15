package com.pemf.vet.ui

import android.os.Build
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.pemf.vet.R
import com.pemf.vet.utils.NotificationHelper
import com.pemf.vet.services.MqttForegroundService
import dagger.hilt.android.AndroidEntryPoint
import android.Manifest
import android.content.pm.PackageManager

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {
    private lateinit var viewPager: ViewPager2
    private lateinit var bottomNav: BottomNavigationView
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Create notification channels
        NotificationHelper.createNotificationChannels(this)
        // Removed MqttKeepAliveService - Paho MQTT has built-in auto-reconnect
        
        // Request notification permission for Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) 
                != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    100
                )
            }
        }
        
        viewPager = findViewById(R.id.view_pager)
        bottomNav = findViewById(R.id.nav_view)
        
        // Setup ViewPager2 with adapter
        viewPager.adapter = MainPagerAdapter(this)
        viewPager.isUserInputEnabled = true // Enable swipe gestures
        
        // Sync BottomNavigationView with ViewPager2
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.navigation_home -> {
                    viewPager.setCurrentItem(0, false)
                    true
                }
                R.id.navigation_session_control -> {
                    viewPager.setCurrentItem(1, false)
                    true
                }
                R.id.navigation_monitor -> {
                    viewPager.setCurrentItem(2, false)
                    true
                }
                R.id.navigation_settings -> {
                    viewPager.setCurrentItem(3, false)
                    true
                }
                else -> false
            }
        }
        
        // Sync ViewPager2 with BottomNavigationView
        viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                super.onPageSelected(position)
                val menuItem = when (position) {
                    0 -> R.id.navigation_home
                    1 -> R.id.navigation_session_control
                    2 -> R.id.navigation_monitor
                    3 -> R.id.navigation_settings
                    else -> R.id.navigation_home
                }
                bottomNav.selectedItemId = menuItem
            }
        })
    }
    
    override fun onResume() {
        super.onResume()
        // Arka plandan döndüğünde herhangi bir özel işlem gerekmiyorsa yorum satırı olarak bırakılabilir
        // StateFlow'lar zaten son değeri otomatik olarak sağlıyor
    }
    
    override fun onDestroy() {
        super.onDestroy()
        // ✅ Uygulama tamamen kapatılıyorsa (swipe to dismiss) service'i durdur
        // Sadece home tuşu ile background'a gönderildiğinde service çalışmaya devam eder
        if (isFinishing) {
            MqttForegroundService.stop(this)
        }
    }
}

